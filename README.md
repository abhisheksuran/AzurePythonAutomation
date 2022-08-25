# AzurePythonAutomation

1) AzureInventory.py ---> This script retrieve information about all the resources in an azure subscription and stores the information into an excel sheet.
data is stored as a separate excel worksheet of each type of resource. After saving data into the excel sheet, it then emails the
excel sheet as an attachment using sendGrid.

2) AzureInventoryResourceClient.py ---> Same as 1st one but it does not uses Azure resource graph for fetching data. And data retreived by this script is less than the 1st one.

3) TakeSnapShots.py  ---> This takes the snapshot of all the disks attached to a virtual machine i.e os disk and data disk, number of data disks per VM can be multiple.