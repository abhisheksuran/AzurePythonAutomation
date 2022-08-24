#!/usr/bin/env python3

"""
Getting all the Azure resources, separating them into different categories and importing to excel sheet and Emailing.
"""

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
import pandas as pd

import os, sys, json, base64, pathlib
from datetime import date
from azure.keyvault.secrets import SecretClient
import automationassets

import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType, Disposition

# Retreiving Key vault name that stores your sendgrid api key from the automation account varitables 	
KEY_VAULT = automationassets.get_automation_variable(str("KEY_VAULT_NAME"))	
# Retreiving name of the Secret inside key vault that contain sendgrid api key.
SG_API_KEY = automationassets.get_automation_variable("sendgridAPIKEY")


class DataCollector:
	"""Collects resources data from Azure and saves them into excel file"""
	def __init__(self, subscription_id):
		self.subscription_id = subscription_id
		self.credential= DefaultAzureCredential()
		self.rm_client = ResourceManagementClient(credential=self.credential, subscription_id=self.subscription_id)
		self.file_path =  os.environ.get("TEMP")
		self._keyVaultName = KEY_VAULT
		

	def get_secret(self, secret_name):
		"""Get a secret from azure key vault"""
		KVUri = f"https://{self._keyVaultName}.vault.azure.net"
		client = SecretClient(vault_url=KVUri, credential=self.credential)
		retrieved_secret = client.get_secret(secret_name).value
		return retrieved_secret
		
	def get_rg_resource(self):
		"""Retrive data from azure and returns 3 things i.e 
		list of resource groups,
		list of all the resources
		and a dictionary of RG with their resources """
		rg_gen_lst = self.rm_client.resource_groups.list()
		# list of resource groups
		rg_lst = []
		# resource group to all the resources in a group dictionary, where key is the rg name and value is the iterator of resources.
		rg_to_res = {}
		while True:
			try:
				rg = next(rg_gen_lst)
				rg_lst.append(rg.as_dict())
				# print(rg)

				# getting resources from a RG
				resources_in_rg = self.rm_client.resources.list_by_resource_group(rg.name)
				res_list = []
				for res in resources_in_rg:
					try:
						res_list.append(res.as_dict())
					except StopIteration:
						break
				rg_to_res[str(rg.name)] = res_list

			except StopIteration:
				print('Chk Pt 1')
				break
		return  rg_lst, res_list, rg_to_res

	def get_resoure_type(self):
		""" This returns 2 items i.e list of resource types and
		a dictionary with resource type as key and list of resources that corresponds to that type """

		# Making a dictionary with keys as type of resource and value as a list of resources
		res_by_type = {}
		_, _, rg_to_res = self.get_rg_resource()

		for rg, value in rg_to_res.items():
			for res in value:
				try:
					tp = res['type']
					res['resource_group'] = rg
					if tp in res_by_type.keys():
						res_by_type[str(tp)].append(res)
					else:
						res_by_type[str(tp)] = [res]
				except:
					print("Resource without any type attribute found!!!")
		#print(res_by_type)
		all_type = [typ for typ in res_by_type.keys()]
		#print(all_type)

		return all_type, res_by_type

	def save_to_excel(self, file_name='AzureInventory.xlsx'):
		"""This converts data into  dataframe and saves them into a excel sheet"""
		file_path = os.path.join(self.file_path, file_name)
		_, res_by_type = self.get_resoure_type()
		# converting dicts to dataframe and mapping dataframe to the excel sheet name.
		all_df = {}
		for typ in res_by_type:
			df = pd.DataFrame(res_by_type[typ])
			sheet_name = str(typ).split('/')[-1]
			if sheet_name in all_df.keys():
				all_df[str(sheet_name)].append(df)
			else:
				all_df[str(sheet_name)] = [df]

		#saving all the dataframes in a excel sheel within different worksheet for each  resource type

		writer = pd.ExcelWriter(file_path, engine='xlsxwriter')

		for sheet, frame in all_df.items():
			frame[0].to_excel(writer, sheet_name=sheet)
		writer.save()

		return file_path


class SendMail:
	"""Send email using sendgrid"""
	def __init__(self, sender_id, recipient_id ,subject='Sample subject',
	  message_body='Test Message', attachment_path=None, sg_api_key=None):
		if sg_api_key is None:
			print("Kindly Enter an Valid sendgrid API key")
			sys.exit()
		self._sg_api_key = sg_api_key
		self.from_email = Email(str(sender_id)) 
		self.recipient_id = To(recipient_id)
		self.subject = subject
		self.message_body = message_body
		self.attachment_path = attachment_path	
		self.sg = self.login()
		
	def login(self):
		"""Login to sendgrid"""
		
		try:
			sg = sendgrid.SendGridAPIClient(api_key=self._sg_api_key)
		except Exception as e:
			print(e)
			print("Credential ERROR!!!")
			sys.exit()
		return sg

	def send(self):
		"""Sends email"""
	
		content = Content("text/plain", self.message_body)
		mail = Mail(self.from_email, self.recipient_id, self.subject, content)

		if self.attachment_path is not None:

			with open(self.attachment_path, 'rb') as f:
				data = f.read()
				f.close()
			encoded_file = base64.b64encode(data).decode()
			file_extension = pathlib.Path(self.attachment_path).suffix
			file_name = pathlib.Path(self.attachment_path).name

			attachedFile = Attachment(
				FileContent(encoded_file),
				FileName(str(file_name)),
				FileType(f'application/{file_extension}'),
				Disposition('attachment')
			)

			mail.attachment = attachedFile

		# Get a JSON-ready representation of the Mail object
		mail_json = mail.get()

		# Send an HTTP POST request to /mail/send
		response = self.sg.client.mail.send.post(request_body=mail_json)
		print(response.status_code)
		print(response.headers)

		return

if __name__ == '__main__':

	try:
		file_name='AzureInventory.xlsx'
		subscription_id = ["<SUBSCRIPTION ID HERE>"]
		data = DataCollector(subscription_id[0])
		attachment_path = data.save_to_excel(file_name)
	except:
		print("Not able to retrieve data!!!")
		sys.exit()

	sg_api_key = data.get_secret(SG_API_KEY)
	#print(sg_api_key)
	from_email = "<SENDGRID VARIFIED SENDER ID HERE>"  # Change to your verified sender
	to_email = "<RECIPIENT ID HERE>"  # Change to your recipient
	subject = f"Azure Inventory on {date.today()}"
	message_body = f"""Hello Team,
Kindly find the Azure inventory as of {date.today()} in the Attachment.

Thanks & Regards,
Azure Automation (pyauto)"""

	mailbox = SendMail(from_email, to_email, subject, message_body, attachment_path, sg_api_key=str(sg_api_key))
	mailbox.send()
