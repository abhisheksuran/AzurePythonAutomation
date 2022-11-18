#!/usr/bin/env python3

"""This Runbook Start/Stop the Postgresql Flexible server.
   This Runbook requires an runas account configured for the Azure automation account.
   Runas Account should have the required permissions to perform start operation on the resource."""


import requests
import time
import automationassets
import sys
# from pprint import pprint


class FlexiAuto:
    def __init__(self, subscription, resource_group, server_name, action):
        self.subscription_id = subscription
        self.resource_group = resource_group
        self.server_name = server_name
        self.action = action
        self.AuthHeader = {'Authorization': 'Bearer ' + self.get_automation_runas_credential()}
        self.current_status = self.get_status()

    @staticmethod
    def get_automation_runas_credential():

        """ This function returns Access Token for working with Azure management API"""

        from OpenSSL import crypto
        import adal

        runas_connection = automationassets.get_automation_connection("AzureRunAsConnection")

        # Get the Azure Automation RunAs service principal certificate
        cert = automationassets.get_automation_certificate("AzureRunAsCertificate")
        pks12_cert = crypto.load_pkcs12(cert)
        pem_pkey = crypto.dump_privatekey(crypto.FILETYPE_PEM,pks12_cert.get_privatekey())

        # Get run as connection information for the Azure Automation service principal
        application_id = runas_connection["ApplicationId"]
        thumbprint = runas_connection["CertificateThumbprint"]
        tenant_id = runas_connection["TenantId"]

        # Authenticate with service principal certificate
        resource = "https://management.core.windows.net/"
        authority_url = ("https://login.microsoftonline.com/"+tenant_id)
        context = adal.AuthenticationContext(authority_url)

        return context.acquire_token_with_client_certificate(
                resource,
                application_id,
                pem_pkey,
                thumbprint)['accessToken']

    def get_status(self):
        """This function returns the info about the flexiserver"""

        url = f'https://management.azure.com/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}/providers/Microsoft.DBForPostgreSql/flexibleServers/{self.server_name}?api-version=2020-02-14-preview'
        try:
            response = requests.get(url, headers=self.AuthHeader)
            res = response.json()
            res = res['properties']
            res = res.get('state', None)
        except Exception as e:
            print("Got ERROR while Getting info for server:", e)
            sys.exit()
        return res

    def get_expected_state(self):
        """This return expected current state before performing action and desired state after action for the server"""
        if self.action == 'start':
            expected_state = 'Stopped'
            desired_state = 'Ready'
        elif self.action == 'stop':
            expected_state = 'Ready'
            desired_state = 'Stopped'
        else:
            raise Exception("Action can only be start or stop")
        return expected_state, desired_state

    def perform_action(self):
        """This performs the action specified by the user"""
        expected_state, desired_state = self.get_expected_state()
        if self.current_status == desired_state:
            print(f"Server {self.server_name} is already in {desired_state} state, Quiting...")
            sys.exit()

        elif self.current_status == expected_state:
            print(f"[+]Trying to {self.action} the Flexi Server {self.server_name}...[+]")
            try:
                url = f'https://management.azure.com/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}/providers/Microsoft.DBForPostgreSql/flexibleServers/{self.server_name}/{self.action}?api-version=2020-02-14-preview'
                response = requests.post(url, json={}, headers=self.AuthHeader)
            except Exception as e:
                print(f'[-]Some Error occured while requesting to {self.action} the flexi server {self.server_name}[-]',
                      e)
                sys.exit()
        else:
            print(
                f"[-]Current Status is {self.current_status} but server {self.server_name}"
                f" state should be {expected_state}, Quiting[-]")
            sys.exit()

        status_code = response.status_code
        if status_code not in [200, 202]:
            print(
                f'Some Error occured while requesting to {self.action} the flexi server.\n STATUS CODE: {status_code}')
            sys.exit()
        else:
            print(f"Request to {self.action} server {self.server_name} was sent successfully.")

        print(f"[+]Getting info for the {self.server_name} Flexi Server...[+]")
        while self.current_status != desired_state:
            print('waiting for 30 sec to check for server status !!!')
            time.sleep(30)
            self.current_status = self.get_status()
            print(self.current_status)
        print(f"[-]Flexi Server {self.server_name} is in {self.action} state now...[-]")
        return True


if __name__ == "__main__":
        subscriptionId = '<ENTER_SUBSCRIPTION_ID_HERE>'  # Subscriptions in which flexible server is present

        # -------------------------- for single server -----------------------------

        resourceGroupName = '<ENTER RG HERE>'  # Resource group for flexible server
        serverName = '<ENTER SERVER NAME HERE>'  # Name of the flexible server
        action = 'start'              # change to stop for stopping the server
        server = FlexiAuto(subscriptionId, resourceGroupName, serverName, action)
        server.perform_action()

        # -------------------------- for multiple servers --------------------------

        # rg_list = ['rg1', 'rg2']                                # list of resource group for the flexible servers
        # server_name_list = ['server1', 'server2']               # list of flexible server in the same order as rg_list
        # action = 'start'                                        # change to stop for stopping the server
        # servers = [FlexiAuto(rg, server) for rg, server in zip(rg_list, server_name_list)]
        # actions = [server.perform_action() for server in servers]
