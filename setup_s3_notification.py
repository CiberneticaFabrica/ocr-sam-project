#!/usr/bin/env python3
"""
Script to configure S3 bucket notification for existing bucket
This needs to be run after SAM deploy since we can't create the bucket in CloudFormation
"""

import boto3
import json
import sys

def setup_s3_notification(bucket_name, lambda_function_arn):
    """Configure S3 bucket notification for Lambda trigger"""
    try:
        s3_client = boto3.client('s3')
        lambda_client = boto3.client('lambda')
        
        print(f"🔧 Setting up S3 notification for bucket: {bucket_name}")
        print(f"🔧 Lambda function ARN: {lambda_function_arn}")
        
        # Add permission for S3 to invoke Lambda
        try:
            lambda_client.add_permission(
                FunctionName=lambda_function_arn,
                StatementId='s3-trigger-permission',
                Action='lambda:InvokeFunction',
                Principal='s3.amazonaws.com',
                SourceArn=f'arn:aws:s3:::{bucket_name}'
            )
            print("✅ Lambda permission added")
        except lambda_client.exceptions.ResourceConflictException:
            print("ℹ️ Lambda permission already exists")
        
        # Configure S3 notification
        notification_config = {
            'LambdaConfigurations': [
                {
                    'Id': 'document-processor-trigger',
                    'LambdaFunctionArn': lambda_function_arn,
                    'Events': ['s3:ObjectCreated:*'],
                    'Filter': {
                        'Key': {
                            'FilterRules': [
                                {
                                    'Name': 'prefix',
                                    'Value': 'incoming/'
                                },
                                {
                                    'Name': 'suffix',
                                    'Value': '.pdf'
                                }
                            ]
                        }
                    }
                }
            ]
        }
        
        s3_client.put_bucket_notification_configuration(
            Bucket=bucket_name,
            NotificationConfiguration=notification_config
        )
        
        print("✅ S3 notification configured successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error setting up S3 notification: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python setup_s3_notification.py <bucket_name> <lambda_function_arn>")
        sys.exit(1)
    
    bucket_name = sys.argv[1]
    lambda_function_arn = sys.argv[2]
    
    success = setup_s3_notification(bucket_name, lambda_function_arn)
    sys.exit(0 if success else 1)
