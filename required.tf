terraform {
  required_providers {
    mycloud = {
      source  = "hashicorp/aws"
      version = "<=3.39.0"
    }
  }
}