locals {
  lambda_zip_path = "outputs/lambda_function_code.zip"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "lambda_code/lambda_function.py"
  output_path = local.lambda_zip_path 
}
resource "aws_lambda_function" "locuz_lambda_function" {
     filename = local.lambda_zip_path
     function_name = "locuz_ebs_automation"
     role = aws_iam_role.iam_role_for_lambda.arn
     handler = "locuz_ebs_automation.lambda_handler"
     source_code_hash = data.archive_file.lambda_zip.output_base64sha256
     runtime = "python3.7"
}