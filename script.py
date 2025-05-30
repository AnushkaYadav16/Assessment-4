import subprocess
import os
import boto3
import io
import zipfile
import tempfile
import time
import sys
import shutil
import argparse
import json
from botocore.exceptions import ClientError
from botocore.config import Config

lambda_config = Config(read_timeout=300, connect_timeout=60)
lambda_client = boto3.client('lambda', config=lambda_config)

# CONFIGURATION (some values from CLI)
LAMBDA_FILE = './lambda_function.py'
ACC_FILE = './get_accounts.py'
TRANS_FILE = './get_transactions.py'       
S3_BUCKET = 'myziplambdabucktanushka1109'
S3_KEY = 'lambda_function.zip'
ACC_KEY = 'get_accounts.zip'
TRANS_KEY = 'get_transactions.zip'
TEMPLATE_PATH = './rds_mysql_template.yaml'
REGION = 'ap-south-1'
LAMBDA_FUNCTION_NAME = 'InitMySQLTables'
STATIC_HTML_FILE = './index.html'
STATIC_BUCKET = 'my-ui-bucket-anushka-1610' 


# CLI ARGUMENT PARSER
def parse_args():
    parser = argparse.ArgumentParser(description="Deploy RDS MySQL with Lambda using CloudFormation")
    parser.add_argument('--stack-name', required=True, help='CloudFormation stack name')
    parser.add_argument('--db-password', required=True, help='Master DB password')
    return parser.parse_args()

# CREATE S3 BUCKET IF NEEDED
def ensure_bucket_exists():
    print(f"Checking S3 bucket: {S3_BUCKET}")
    s3 = boto3.client('s3', region_name=REGION)
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        print(f"S3 bucket '{S3_BUCKET}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Bucket '{S3_BUCKET}' not found. Creating...")
            config = {'LocationConstraint': 'ap-south-1'} 
            s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration=config)
            print(f"Bucket '{S3_BUCKET}' created.")
        else:
            raise

# PACKAGE AND UPLOAD LAMBDA IN MEMORY
def package_and_upload_lambda(zipfiles, key):
    print("Packaging Lambda function in-memory...")

    with tempfile.TemporaryDirectory() as temp_dir:
        shutil.copy(zipfiles, temp_dir)

        subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'pymysql', '-t', temp_dir
        ], check=True)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
        zip_buffer.seek(0)

        s3 = boto3.client('s3', region_name=REGION)
        s3.upload_fileobj(zip_buffer, S3_BUCKET, key)
        print(f"Uploaded Lambda zip to s3://{S3_BUCKET}/{key}")

# creating security group
def get_or_create_lambda_sg(vpc_id, region):
    ec2 = boto3.client('ec2', region_name=region)

    # Check if SG already exists
    groups = ec2.describe_security_groups(
        Filters=[{'Name': 'group-name', 'Values': ['LambdaAccessToRDS']}]
    )
    if groups['SecurityGroups']:
        return groups['SecurityGroups'][0]['GroupId']

    # Create the SG
    sg = ec2.create_security_group(
        GroupName='LambdaAccessToRDS',
        Description='Allow Lambda to connect to RDS',
        VpcId=vpc_id
    )

    try:
        ec2.authorize_security_group_egress(
            GroupId=sg['GroupId'],
            IpPermissions=[{
                'IpProtocol': '-1',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }]
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidPermission.Duplicate':
            print("Egress rule already exists. Continuing...")
        else:
            raise

    return sg['GroupId']

# DEPLOY CLOUDFORMATION STACK
def deploy_stack(stack_name, db_password):
    print(f"Deploying stack: {stack_name}")

    ec2 = boto3.client('ec2', region_name=REGION)
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    vpc_id = vpcs['Vpcs'][0]['VpcId']
    sg_id = get_or_create_lambda_sg(vpc_id, REGION)


    subprocess.run([
        'aws', 'cloudformation', 'deploy',
        '--template-file', TEMPLATE_PATH,
        '--stack-name', stack_name,
        '--capabilities', 'CAPABILITY_NAMED_IAM',
        '--parameter-overrides', 
        f'DBPassword={db_password}',
        f'S3Bucket={S3_BUCKET}',
        f'S3Key={S3_KEY}',
        f'ACCKey={ACC_KEY}',
        f'TRANSKey={TRANS_KEY}',
        f'LambdaSG={sg_id}',
        f'VPC={vpc_id}'
    ], check=True)

    print("Waiting for stack deployment...")
    cf = boto3.client('cloudformation', region_name=REGION)
    waiter = cf.get_waiter('stack_create_complete')
    waiter.wait(StackName=stack_name)
    print(f"Stack '{stack_name}' deployed successfully.")

# UI
def upload_static_site():
    s3 = boto3.client('s3', region_name=REGION)

    print(f"Checking/creating static site bucket: {STATIC_BUCKET}")
    try:
        s3.head_bucket(Bucket=STATIC_BUCKET)
        print(f"Bucket '{STATIC_BUCKET}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            s3.create_bucket(
                Bucket=STATIC_BUCKET,
                CreateBucketConfiguration={'LocationConstraint': REGION}
            )
            print(f"Bucket '{STATIC_BUCKET}' created.")
        else:
            raise

    print(f"Uploading {STATIC_HTML_FILE}...")
    with open(STATIC_HTML_FILE, 'rb') as f:
        s3.put_object(
            Bucket=STATIC_BUCKET,
            Key='index.html',
            Body=f,
            ContentType='text/html'
        )

    print("Disabling Block Public Access settings...")
    s3.put_public_access_block(
        Bucket=STATIC_BUCKET,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': False,
            'IgnorePublicAcls': False,
            'BlockPublicPolicy': False,
            'RestrictPublicBuckets': False
        }
    )

    print("Setting public-read policy...")
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{STATIC_BUCKET}/*"
        }]
    }

    s3.put_bucket_policy(
        Bucket=STATIC_BUCKET,
        Policy=json.dumps(policy)
    )

    print("Enabling static website hosting...")
    s3.put_bucket_website(
        Bucket=STATIC_BUCKET,
        WebsiteConfiguration={
            'IndexDocument': {'Suffix': 'index.html'},
            'ErrorDocument': {'Key': 'index.html'}
        }
    )

    # site_url = f"http://{STATIC_BUCKET}.s3-website-{REGION}.amazonaws.com/"
    # http://my-ui-bucket-anushka-1610.s3-website.ap-south-1.amazonaws.com/
    site_url2 = f"http://my-ui-bucket-anushka-1610.s3-website.ap-south-1.amazonaws.com/"
    # print(f"\n✅ Static site is live at:\n{site_url}")
    print(f"\n✅ Static site is live at:\n{site_url2}")

# INVOKE LAMBDA FUNCTION
def invoke_lambda():
    print("Invoking Lambda function...")
    lambda_client = boto3.client('lambda', region_name=REGION)
    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType='RequestResponse'
    )
    result = response['Payload'].read().decode()
    print("Lambda response:\n", result)

# MAIN
if __name__ == '__main__':
    args = parse_args()
    ensure_bucket_exists()
    package_and_upload_lambda(LAMBDA_FILE, S3_KEY)
    package_and_upload_lambda(ACC_FILE, ACC_KEY)
    package_and_upload_lambda(TRANS_FILE, TRANS_KEY)
    deploy_stack(args.stack_name, args.db_password)
    invoke_lambda()
    upload_static_site()