provider "aws" {
  region = "us-west-2"  
}

data "terraform_remote_state" "stack1" {
  backend = "local"
  config = {
    path = "../stack1/terraform.tfstate.d/rebuild/terraform.tfstate"
  }
}

module "bedrock_kb" {
  source = "../modules/bedrock_kb" 

  knowledge_base_name        = "my-bedrock-kb"
  knowledge_base_description = "Knowledge base connected to Aurora Serverless database"

  aurora_arn        = data.terraform_remote_state.stack1.outputs.aurora_arn
  aurora_db_name    = "myapp"
  aurora_endpoint   = data.terraform_remote_state.stack1.outputs.aurora_endpoint
  aurora_table_name = "bedrock_integration.bedrock_kb"
  aurora_primary_key_field = "id"
  aurora_metadata_field = "metadata"
  aurora_text_field = "chunks"
  aurora_verctor_field = "embedding"
  aurora_username   = "dbadmin"
  aurora_secret_arn = data.terraform_remote_state.stack1.outputs.rds_secret_arn
  s3_bucket_arn = data.terraform_remote_state.stack1.outputs.s3_bucket_name
}