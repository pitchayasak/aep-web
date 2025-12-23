from flask import Flask, redirect, url_for, render_template, request, make_response, session

from azure.storage.blob import BlobServiceClient

import time
from datetime import datetime, timezone
import uuid
import random
import requests
import pandas as pd
import math

import json
import os

# -----------------------------------------------------------------------------------------------------------------
# Start Regular Function Here

def round_up_decimal(number, decimals=0):
    """Rounds a number up to a specified number of decimal places."""
    if decimals == 0:
        return math.ceil(number)
    multiplier = 10**decimals
    return math.ceil(number * multiplier) / multiplier

def load_secrets(filename="aep-api.json"):
    """
    Reads a JSON file and returns the data as a Python dictionary.
    """
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: The file {filename} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from the file {filename}.")
        return None

def get_bearer_token(aep_secret):
    url = "https://ims-na1.adobelogin.com/ims/token/v3"

    headers = {        
        "Content-Type": "application/x-www-form-urlencoded"
    }
 
    data = {
        "grant_type" :  "client_credentials",
        "client_id" : aep_secret.get("client_id"),
        "client_secret" : aep_secret.get("client_secret"),
        "scope" : "openid,AdobeID,read_organizations,additional_info.projectedProductContext,session"
    }
    
    response = requests.post(url, headers=headers, data=data)
    
    #print(f"Status Code: {response.status_code}")
    #print(f"Response: {response.text}")
    _b = json.loads(response.text)
    _b['expires_timestamp'] = time.time() + 86000
    _b['sandbox_name'] = aep_secret.get("x-sandbox-name")
    return _b

def get_source_credentials(aep_secret,bearer_token,sandbox_name):
    url = f"https://platform.adobe.io/data/foundation/connectors/landingzone/credentials"

    params = {
        'type': 'user_drop_zone'
    }
    
    headers = {        
        "Authorization" : f"Bearer {bearer_token['access_token']}",
        "x-api-key" : aep_secret.get("x-api-key"),
        "x-gw-ims-org-id" : aep_secret.get("x-gw-ims-org-id"),
        "x-sandbox-name" : sandbox_name,
        "Cache-Control" : "no-cache"        
    }
      
    response = requests.get(url,headers=headers,params=params)

    # print(f"status code : {response.status_code}")
    # print(f"response : {response.text}")
    _c = json.loads(response.text)
    _c['sandbox_name'] = sandbox_name
    return _c

def get_destination_credentials(aep_secret,bearer_token,sandbox_name):
    url = f"https://platform.adobe.io/data/foundation/connectors/landingzone/credentials?type=dlz_destination"
    
    headers = {        
        "Authorization" : f"Bearer {bearer_token['access_token']}",
        "x-api-key" : aep_secret.get("x-api-key"),
        "x-gw-ims-org-id" : aep_secret.get("x-gw-ims-org-id"),
        "x-sandbox-name" : sandbox_name,
        "Cache-Control" : "no-cache"        
    }
      
    response = requests.get(url,headers=headers)

    # print(f"status code : {response.status_code}")
    # print(f"response : {response.text}")
    _c = json.loads(response.text)
    _c['sandbox_name'] = sandbox_name
    return _c
    
all_secrets = load_secrets()

if all_secrets:
    pass
    # Access a top-level secret
    # aep_secret = all_secrets.get("prod")
    # print(f"aep_secret: {aep_secret}")

    # Access a nested secret
    # client_id = all_secrets.get("prod", {}).get("client_id")
    # print(f"client_id: {client_id}")
else:
    print("Main Secrets not found. Please check file [aep-api.json]")
    exit()

# -----------------------------------------------------------------------------------------------------------------
# Start Flask Here

app = Flask(__name__)

app.secret_key = 'for-bay-only'

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/setenv', methods = ['POST','GET']) 
def setenv():
    if request.method == 'POST':
        is_vpn = request.form.get('VPN')        
        sandbox_name = request.form.get('sandbox')
        resp = make_response(render_template('navigator.html',is_vpn=is_vpn,sandbox_name=sandbox_name))
        session['is_vpn'] = is_vpn
        session['sandbox_name'] = sandbox_name

        if is_vpn:
            os.environ["HTTP_PROXY"] = "proxyinternet.krungsri.net:8080"
            os.environ["HTTPS_PROXY"] = "proxyinternet.krungsri.net:8080"
        return resp

@app.route('/source_list_all_files') 
def source_list_all_files():
    return render_template("dlz_list_all_files.html", title='Source list all files',sandbox_name=session['sandbox_name'], dlz_type='source')

@app.route('/api/source_list_all_files')
def api_source_list_all_files():
    aep_secret = all_secrets.get(session['sandbox_name'])

    if 'sandbox_name' not in session:
        return redirect(url_for('/'))

    if 'source_credentials' in session:
        if 'sandbox_name' not in session['source_credentials']:
            session['source_credentials'] = get_source_credentials(aep_secret=aep_secret,bearer_token=session['bearer_token'],sandbox_name=session['sandbox_name'])
        else:
            if session['sandbox_name'] == session['source_credentials']['sandbox_name']:
                pass
            else:
                session['source_credentials'] = get_source_credentials(aep_secret=aep_secret,bearer_token=session['bearer_token'],sandbox_name=session['sandbox_name'])
    else:
        if 'bearer_token' not in session:
            session['bearer_token'] = get_bearer_token(aep_secret)

        if 'sandbox_name' not in session['bearer_token']:
            session['bearer_token'] = get_bearer_token(aep_secret)
        
        if session['sandbox_name'] != session['bearer_token']['sandbox_name']:
            session['bearer_token'] = get_bearer_token(aep_secret)
        
        if time.time() > session['bearer_token']['expires_timestamp']:
            session['bearer_token'][session['sandbox_name']] = get_bearer_token(aep_secret)
        
        session['source_credentials'] = get_source_credentials(aep_secret=aep_secret,bearer_token=session['bearer_token'],sandbox_name=session['sandbox_name'])

    account_url = f"https://{session['source_credentials']['storageAccountName']}.blob.core.windows.net"
    blob_service_client = BlobServiceClient(account_url, credential=session['source_credentials']['SASToken'])
    
    container_client = blob_service_client.get_container_client(container=session['source_credentials']['containerName'])
    blobs_list = container_client.list_blobs()

    _list = {"data":[]}
    for blob in blobs_list:
        _d = {}
        _d['name'] = blob.name
        _d['creation_time'] = blob.creation_time
        _d['last_modified'] = blob.last_modified
        _d['size'] = round_up_decimal(blob.size / (1024 * 1024), 2)
        _list['data'].append(_d)

    return _list

@app.route('/destination_list_all_files') 
def destination_list_all_files():
    return render_template("dlz_list_all_files.html", title='destination list all files',sandbox_name=session['sandbox_name'], dlz_type='destination')

@app.route('/api/destination_list_all_files')
def api_destination_list_all_files():
    aep_secret = all_secrets.get(session['sandbox_name'])

    if 'sandbox_name' not in session:
        return redirect(url_for('/'))

    if 'destination_credentials' in session:
        if 'sandbox_name' not in session['destination_credentials']:
            session['destination_credentials'] = get_destination_credentials(aep_secret=aep_secret,bearer_token=session['bearer_token'],sandbox_name=session['sandbox_name'])
        else:
            if session['sandbox_name'] == session['destination_credentials']['sandbox_name']:
                pass
            else:
                session['destination_credentials'] = get_destination_credentials(aep_secret=aep_secret,bearer_token=session['bearer_token'],sandbox_name=session['sandbox_name'])
    else:
        if 'bearer_token' not in session:
            session['bearer_token'] = get_bearer_token(aep_secret)
        
        if 'sandbox_name' not in session['bearer_token']:
            session['bearer_token'] = get_bearer_token(aep_secret)

        if session['sandbox_name'] != session['bearer_token']['sandbox_name']:
            session['bearer_token'] = get_bearer_token(aep_secret)
        
        if time.time() > session['bearer_token']['expires_timestamp']:
            session['bearer_token'] = get_bearer_token(aep_secret)
        
        session['destination_credentials'] = get_destination_credentials(aep_secret=aep_secret,bearer_token=session['bearer_token'],sandbox_name=session['sandbox_name'])

    account_url = f"https://{session['destination_credentials']['storageAccountName']}.blob.core.windows.net"
    blob_service_client = BlobServiceClient(account_url, credential=session['destination_credentials']['SASToken'])
    
    container_client = blob_service_client.get_container_client(container=session['destination_credentials']['containerName'])
    blobs_list = container_client.list_blobs()

    _list = {"data":[]}
    for blob in blobs_list:
        _d = {}
        _d['name'] = blob.name
        _d['creation_time'] = blob.creation_time
        _d['last_modified'] = blob.last_modified
        _d['size'] = round_up_decimal(blob.size / (1024 * 1024), 2)
        _list['data'].append(_d)

    return _list

# -----------------------------------------------------------------------------------------------------------------


if __name__ == '__main__':
    app.run(debug=False) # Do not use debug=True here when debugging with VS Code


# -----------------------------------------------------------------------------------------------------------------
