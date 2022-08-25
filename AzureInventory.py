#!/usr/bin/env python3
"""This script retreive information about all the resources in the azure subscription and stores the information into an excel sheet.
data is stored as a separate excel worksheet to each type of resource. After saving data into the excel sheet, it then sends the
excel sheet as an attachment into an email using sendGrid."""

import os
from pprint import pprint
import pandas as pd
import azure.mgmt.resourcegraph as arg
from azure.identity import DefaultAzureCredential
import os, sys, json, base64, pathlib
from datetime import date
from azure.keyvault.secrets import SecretClient
#from azure.mgmt.resource import SubscriptionClient
import automationassets

import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType, Disposition


# Retreiving Key vault name that stores your sendgrid api key from the automation account varitables 
KEY_VAULT = automationassets.get_automation_variable(str("KEY_VAULT_NAME"))  #change to your own variable name 
# Retreiving name of the Secret inside key vault that contain sendgrid api key.
SG_API_KEY = automationassets.get_automation_variable("sendgridAPIKEY")      # change to your own variable name


class NestedToSimpleDict:
	"""This class converts a JSON data which is a nested python dictionary into a simple dictionary with no nesting."""
	def __init__(self, data, separator='_'):
		self.data = data
		self.separator = separator
		self.simple_dict = {}
		self._to_single_dict(data)

	def _is_list(self, value, last_name):
		for i, d in enumerate(value):
			last_name = last_name + str(self.separator) + str(i)
			self._to_single_dict(d, last_name)
		return None

	def _to_single_dict(self, d,last_key=None):
		for key, value in d.items():
			if isinstance(value, dict):
				for k,v in value.items():
					if last_key is None:
						new_key = str(key) + str(self.separator) + str(k)
					else:
						new_key = str(last_key) + str(self.separator) + str(key) + str(self.separator) + str(k)
					if isinstance(v, dict):
						self._to_single_dict(v, new_key)

					elif isinstance(v, list) and len(v) !=0 and all(isinstance(item, dict) for item in v):
						self._is_list(v, last_name=new_key)

					else:
						self.simple_dict[new_key] = v
			elif isinstance(value, list) and len(value) !=0 and all(isinstance(item, dict) for item in value):
				if last_key is None:
					self._is_list(value, last_name='')
				else:
					self._is_list(value, last_name=last_key)

			else:
				if last_key is None:
					self.simple_dict[str(key)] = value
				else:
					self.simple_dict[str(last_key) + str(self.separator) + str(key)] = value
		return None


class DataCollector:
	"""Collects resources data from Azure and saves them into excel file"""
	def __init__(self, subscription_id):
		self.subscription_id = subscription_id
		self.credential= DefaultAzureCredential()
		self.file_path =  os.environ.get("TEMP")
		self._keyVaultName = KEY_VAULT

	# def get_subscriptions(self):
	# 	"""Get all the subscriptions"""
	# 	subsClient = SubscriptionClient(self.credential)
	# 	subsRaw = []
	# 	for sub in subsClient.subscriptions.list():
	# 		subsRaw.append(sub.as_dict())
	# 	subsList = []
	# 	for sub in subsRaw:
	# 		subsList.append(sub.get('subscription_id'))

	# 	return subsList

	def get_secret(self, secret_name):
		"""Get a secret from azure key vault"""
		KVUri = f"https://{self._keyVaultName}.vault.azure.net"
		client = SecretClient(vault_url=KVUri, credential=self.credential)
		retrieved_secret = client.get_secret(secret_name).value
		return retrieved_secret

	def arg_login_setup(self, res_format="objectArray"):
		"""Creating azure resource graph client."""
		argClient = arg.ResourceGraphClient(self.credential)
		argQueryOptions = arg.models.QueryRequestOptions(result_format=res_format)

		return argClient, argQueryOptions
	
	def get_resources(self, query="resources"):
		"""This returns a list containing info of each resource as a dictionary"""

		try:		
			argClient, argQueryOptions = self.arg_login_setup()

			# Create query
			argQuery = arg.models.QueryRequest(subscriptions=[self.subscription_id], query=query, options=argQueryOptions)

			# Run query
			argResults = argClient.resources(argQuery)

			res = argResults.as_dict()['data']

		except Exception as e:
			print(e)
			print("Error Retreiving data from resource graph!!!")

		data_list = [] 
		for r in res:
			sd = NestedToSimpleDict(r)
			data_list.append(sd.simple_dict)

		return data_list

	def get_resoure_type(self):
		""" This returns 2 items i.e list of resource types and
		a dictionary with resource type as key and list of resources that corresponds to that type """
	
		data_list = self.get_resources()
		
		# Making a dictionary with keys as type of resource and value as a list of resources
		res_by_type = {}

		for res in data_list:
				try:
					tp = res['type']
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
	except Exception as e:
		print(e)
		print("Not able to retrieve data!!!")
		sys.exit()

	sg_api_key = data.get_secret(SG_API_KEY)
	#print(sg_api_key)
	from_email = "<ENTER EMAIL ADDRESS OF THE SEND GRIDE VERIDIED SENDER>"  # Change to your verified sender
	to_email = "<ENTER EMAIL ADDRESS OF RECIPENT>"  # Change to your recipient
	subject = f"Azure Inventory on {date.today()}"
	message_body = f"""Hello Team,
Kindly find the Azure inventory as of {date.today()} in the Attachment.

Thanks & Regards,
Azure Automation (pyauto)"""

	mailbox = SendMail(from_email, to_email, subject, message_body, attachment_path, sg_api_key=str(sg_api_key))
	mailbox.send()
