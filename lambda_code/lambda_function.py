import boto3
import datetime
import time
ec2_cli = boto3.client(service_name="ec2", region_name="ap-south-1")
volume_list = ["vol-049f34ebe171aad93", "vol-0e8e1cd39643fd3f0"]
vol_map = ["/dev/sdf", "/dev/sdg"]
avai_zone = 'ap-south-1b'
account_id = 'XXXXXXXXXX272'
instance_id = 'i-XXXXXXXXXddd2'
    


def lambda_handler(event, context):
    snapshot_list = []
    list_new_vol = []
    # Function for get instance status ##########
    def get_instance_state(instanceid):
        response = ec2_cli.describe_instances(InstanceIds=[instanceid])
        return response['Reservations'][0]['Instances'][0]['State']['Name']

    # Function for instance power on or off
    def instance_on_off(instanceid, status):
        try:
            if status == 'on':
                if 'running' == get_instance_state(instanceid):
                    print('***Warning!! instance :', instanceid, ' already running')
                else:
                    ionstatus = ec2_cli.start_instances(InstanceIds=[instanceid])
                    if ionstatus['ResponseMetadata']['HTTPStatusCode'] == 200:
                        print('***Success!! instance :', instanceid, ' is going to start')
            elif status == 'off':
                if 'stopped' == get_instance_state(instanceid):
                    print('***Warning!! instance :', instanceid, ' already stopped')
                    return 'stopped'
                else:
                    ioffstatus = ec2_cli.stop_instances(InstanceIds=[instanceid])
                    if ioffstatus['ResponseMetadata']['HTTPStatusCode'] == 200:
                        instance_stop_waiter = ec2_cli.get_waiter('instance_stopped')
                        instance_stop_waiter.wait(InstanceIds=[instanceid])
                        print('***Success!! instance :', instanceid, ' is stopped')
                        return 'stopped'
            else:
                print("invaild input")
        except Exception as e:
            print('***Error - Failed to instance: ', instanceid, status)
            print(type(e), ':', e)
            return 'error'

    # Function for get latest snapshot
    def find_snapshots(vol, accountid):
        list_of_snaps = []
        latest_snap_id = ''
        while len(latest_snap_id) < 1:
            for snapshot in ec2_cli.describe_snapshots(Filters=[{'Name':'description','Values':['Created by lambda function for raid disks']},{'Name':'volume-id','Values':[vol]}],OwnerIds=[accountid])['Snapshots']:
                snapshot_volume = snapshot['VolumeId']
                mnt_vol = vol
                if mnt_vol == snapshot_volume:
                    list_of_snaps.append({'date': snapshot['StartTime'], 'snap_id': snapshot['SnapshotId']})
                    # sort snapshots order by date
                    newlist = sorted(list_of_snaps, key=lambda k: k['date'], reverse=True)
                    latest_snap_id = newlist[0]['snap_id']
            if len(latest_snap_id) == 0:
                time.sleep(5)
        # The latest_snap_id provides the exact output snapshot ID
        snapshot_list.append(latest_snap_id)
        return latest_snap_id

    def check_volume_exist(snapid, avaizone):
        response = ec2_cli.describe_volumes(
            Filters=[{'Name': 'snapshot-id', 'Values': [snapid]},
                     {'Name': 'availability-zone', 'Values': [avaizone]},
                     {'Name': 'status', 'Values': ['available']}])
        if len(response['Volumes']) != 0:
            vol_id = response['Volumes'][0]['VolumeId']
            list_new_vol.append(vol_id)
            print("***Volume Id:", vol_id, "is already created")
            return vol_id
        else:
            return 'VolumeNotFound'

    # Function for creat volume
    def create_volume_from_snapshot(volumelist, avaizone, accountid):
        try:
            i = 0
            for volume in volumelist:
                i = i + 1
                snapid = find_snapshots(volume, accountid)
                # print(snapid)
                if 'VolumeNotFound' == check_volume_exist(snapid, avaizone):
                    response = ec2_cli.create_volume(
                        AvailabilityZone=avaizone,
                        Encrypted=False,
                        SnapshotId=snapid,
                        VolumeType='gp2',
                        TagSpecifications=[
                            {
                                'ResourceType': 'volume',
                                'Tags': [{'Key': 'Name', 'Value': ('raid_disk-' + str(i))}, ]
                            },
                        ],
                    )
                    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                        volume_id = response['VolumeId']
                        list_new_vol.append(volume_id)
                        print('***Success!! New volume:', volume_id, 'is creating...')
        except Exception as e:
            print('***Error - Failed to creating new volume.')
            print(type(e), ':', e)

    # Function for get old volume Id
    def get_old_volume_id(instanceid, volmap):
        old_attach_list = []
        for device in volmap:
            response = ec2_cli.describe_volumes(Filters=[{'Name': 'attachment.device', 'Values': [device]},
                                                         {'Name': 'attachment.instance-id', 'Values': [instanceid]},
                                                         {'Name': 'status', 'Values': ['in-use']}])
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                if len(response['Volumes']) != 0:
                    old_attach_list.append(response['Volumes'][0]['VolumeId'])
        return old_attach_list

    # Function for detach old volume Id
    def detach_volume(instanceid, volmap, new_vol):
        try:
            old_volumes = get_old_volume_id(instanceid, volmap)
            if len(old_volumes) != 0:
                # detach the volumes
                for old_vol in old_volumes:
                    if old_vol != new_vol[0] and old_vol != new_vol[1]:
                        detach_response = ec2_cli.detach_volume(VolumeId=old_vol)
                        if detach_response['ResponseMetadata']['HTTPStatusCode'] == 200:
                            print('***Success!! old-volume:', old_vol, 'is detaching from instance: ', instanceid)

                # detach waiter
                for oldvol in old_volumes:
                    if oldvol != new_vol[0] and oldvol != new_vol[1]:
                        if 'available' == get_volume_status(oldvol):
                            print('***Success!! old-volume:', oldvol, 'is detached from instance: ', instanceid)
                        else:
                            volume_detach_waiter = ec2_cli.get_waiter('volume_available')
                            volume_detach_waiter.wait(VolumeIds=[oldvol])
                            print('***Success!! old-volume:', oldvol, 'is detached from instance: ', instanceid)
        except Exception as e:
            print('***Error - Failed to volume detach.')
            print(type(e), ':', e)

    # Function for get volume status
    def get_volume_status(new_vol):
        response = ec2_cli.describe_volumes(VolumeIds=[new_vol])
        return response['Volumes'][0]['State']

    def attach_volume(listnewvol, volmap, instanceid):
        try:
            # Check new volume status before attach volume
            if len(listnewvol) == 2:
                for new_vol in listnewvol:
                    new_vol_status = get_volume_status(new_vol)
                    if 'available' == new_vol_status or 'in-use' == new_vol_status:
                        print('***Success!! New-volume:', new_vol, 'is created')
                    else:
                        volume_create_waiter = ec2_cli.get_waiter('volume_available')
                        volume_create_waiter.wait(VolumeIds=[new_vol])
                        print('***Success!! New-volume:', new_vol, 'is created')

                # Attach new volume
                for y in range(0, 2):
                    if 'available' == get_volume_status(listnewvol[y]):
                        atachresponse = ec2_cli.attach_volume(
                            Device=volmap[y],
                            InstanceId=instanceid,
                            VolumeId=listnewvol[y]
                        )
                        if atachresponse['ResponseMetadata']['HTTPStatusCode'] == 200:
                            print('***Success!! New volume:', listnewvol[y], 'is attaching with instance:', instanceid)

                for new_volume in listnewvol:
                    if 'in-use' == get_volume_status(new_volume):
                        print('***Success!! New-volume:', new_volume, 'is attached')
                    else:
                        volume_create_waiter = ec2_cli.get_waiter('volume_in_use')
                        volume_create_waiter.wait(VolumeIds=[new_volume])
                        print('***Success!! New-volume:', new_volume, 'is attached')
            return 'success'
        except Exception as e:
            print('***Error - Failed to volume detach and attach.')
            print(type(e), ':', e)
            return 'error'

    def get_old_volume_using_tag(avaizone, listnewvol):
        tag_list = ['raid_disk-1', 'raid_disk-2']
        list_old_vol = []
        for tagname in tag_list:
            response = ec2_cli.describe_volumes(Filters=[{'Name': 'tag:Name', 'Values': [tagname]},
                                                         {'Name': 'status', 'Values': ['available']},
                                                         {'Name': 'availability-zone', 'Values': [avaizone]}])
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                if len(response['Volumes']) != 0:
                    for i in range(0, len(response['Volumes'])):
                        oldvol = response['Volumes'][i]['VolumeId']
                        if oldvol != listnewvol[0] and oldvol != listnewvol[1]:
                        # print(response['Volumes'][i]['VolumeId'])
                            list_old_vol.append(oldvol)
        return list_old_vol

    def old_volume_delete(avaizone, listnewvol):
        listoldvol = get_old_volume_using_tag(avaizone,listnewvol)
        if len(listoldvol) != 0:
            for vol in listoldvol:
                removeresponse = ec2_cli.delete_volume(VolumeId=vol)
                if removeresponse['ResponseMetadata']['HTTPStatusCode'] == 200:
                    print('***Success!! old volume:', vol, 'is deleted')

    # Calling all  function
    print('***Destination lambda job start time', datetime.datetime.now())
    # call instance power off function
    instance_state = instance_on_off(instance_id, status='off')
    if instance_state == 'stopped' and len(list_new_vol) == 0:
        # call function for volume creation
        create_volume_from_snapshot(volume_list, avai_zone, account_id)
        print('***New Volumes lists:', list_new_vol)
        # call function for detach and attache volume
        if len(list_new_vol) == 2:
            # call function for volume detach
            detach_volume(instance_id, vol_map, list_new_vol)
            if 'success' == attach_volume(list_new_vol, vol_map, instance_id):
                # call function for instance power on
                instance_on_off(instance_id, status='on')
                # call function for delete old volume
                old_volume_delete(avai_zone, list_new_vol)
            else:
                print('***Error!! Failed to attach volume. See attach_volume function')
        else:
            print('***Error!! Failed Create volume')
    else:
        print('****Error!! Instance stopped failed or volume created more than requested')
        print('Volumes Lists:', list_new_vol)
    print('***Destination lambda job end time', datetime.datetime.now())
