#!/usr/bin/env python3

"""This script take snapshot of all the disk (os and data) for a Vm, u can also update the script to work for multiple vms"""

import azure.mgmt.resourcegraph as arg
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential
from datetime import date, datetime
import automationassets
import sys, json


# Get snapshot_tags variable from the automation account variables
TAGS = automationassets.get_automation_variable("snapshot_tags")
#subscription_id = [automationassets.get_automation_variable("subscription_id")]

#tags = {'CHANGE': 'CH12345'}
try:
	print(TAGS)
	print(json.loads(TAGS))
	print(type(json.loads(TAGS)))
	tags = json.loads(TAGS)

except:
	print("Kindly check snapshot_tags variable for the automation account, It should be a valid python dictionary")
	sys.exit()


class SnapIt:

	def __init__(self, subscription_id):
		self.subscription_id = subscription_id[0]
		self.credential = DefaultAzureCredential()
		try:
			self.compute_client = ComputeManagementClient(self.credential, self.subscription_id)
			self.argClient = arg.ResourceGraphClient(self.credential)
		except:
			print("Kindly check for credentials and subscriptions id. Can't Login ")
			sys.exit()
		
	
	def run_query(self, query):
		"""Runs azure resouce graph query"""
		
		argQueryOptions = arg.models.QueryRequestOptions(result_format="objectArray")
		# Create query
		argQuery = arg.models.QueryRequest(subscriptions=subscription_id, query=query, options=argQueryOptions)
		# Run query
		argResults = self.argClient.resources(argQuery)
		data = argResults.as_dict()['data']
		return data


	def get_vm_data(self, vm_name):
		"""Get details for a vm"""

		get_vm = f"""Resources
		| where type has "microsoft.compute/virtualmachines"
		| extend name = tostring(name)
		| where  name == '{vm_name}'
		| project id, name, subscriptionId, resourceGroup, location, properties.extended.instanceView.powerState.displayStatus"""
		try:
			vm_data = self.run_query(get_vm)
		except Exception as e:
			print(e)
			print(f"Can't Retreive data for VM {vm_name}!!!")
			sys.exit()

		if len(vm_data) > 1:
			print('More Than one vms available with the same name. Quiting...')
			sys.exit()

		if len(vm_data) == 0:
			print('No Virtual machine with this name exists. Quiting...') 
			sys.exit()

		return vm_data

	def get_disk_data(self, vm_id):
		"""Get all the disks for a vm"""

		get_disk = f"""Resources
		| where type has "microsoft.compute/disks"
		| extend diskState = tostring(properties.diskState)
		| where  diskState == 'Attached' and managedBy == "{vm_id}"
		| project id, name, diskState, managedBy, subscriptionId, resourceGroup, location, properties.osType"""
		try:
			disk_data = self.run_query(get_disk)
		except Exception as e:
			print(e)
			print("Not able to retreive data for disk !!!")
			sys.exit()

		return disk_data

	def take_snap(self, disk_data, tags):
		"""Takes snaphot for a disk"""
		try:
			time = datetime.now()
			# snapshot name consists of date time for the zone on which code is running. Need to modify code for a specific zone time.
			snap_name = f'{disk_data["name"]}_{date.today()}_{time.hour}{time.minute}{time.second}'
			async_snapshot_creation = self.compute_client.snapshots.begin_create_or_update(
					f'{disk_data["resourceGroup"]}',
					f'{snap_name}',
					{
						'location': disk_data["location"],
						'tags': tags,
						'creation_data': {
							'create_option': 'Copy',
							'source_uri': disk_data["id"]
						},
						'incremental':False
					}
				)
			snapshot = async_snapshot_creation.result()
		except Exception as e:
			print(e)
			print("ERROR while taking SnapShot!!!")
			sys.exit()
		return snapshot


if __name__ == "__main__":

	subscription_id = ["<SUBSCRIPTION ID>"] # change for subscription id
	vm_name = 'vm1-1'
	snapit_inst = SnapIt(subscription_id)
	vm_data = snapit_inst.get_vm_data(vm_name)
	vm_id = vm_data[0]['id']
	disk_data = snapit_inst.get_disk_data(vm_id)

	data_disk = []

	for disk in disk_data:
		if disk['properties_osType'] is None:
			data_disk.append(disk)
		else:
			os_disk = disk

	#data_disks = [d for d in disk_data if d.properties_osType is None]

	print(f"Taking SnapShot for the Os disk for VM {vm_name}")

	os_snapshot = snapit_inst.take_snap(os_disk, tags).as_dict()

	print(f"Taking SnapShot for all the data disk attached to the VM {vm_name}")

	data_snapshots = []
	for disk in data_disk:
		snap = snapit_inst.take_snap(disk, tags)
		data_snapshots.append(snap.as_dict())

	print(os_snapshot)
	print(data_snapshots)

