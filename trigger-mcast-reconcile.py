#!/usr/bin/env python3

#
# Copyright (c) 2021, Arista Networks, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#   Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
#
#   Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
#   Neither the name of Arista Networks nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# 'AS IS' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

__author__ = 'Petr Ankudinov'

import json
import sys
import argparse
import getpass
import logging

import requests
import requests.packages.urllib3 as urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CVP(object):

    def __init__(self, url_prefix, cvp_username, cvp_password):
        self.session = requests.session()
        self.session.verify = False
        self.cvp_url_prefix = url_prefix
        self.timeout = 180
        self.temp_task_list = list()  # list of temp tasks to save and execute
        # authenticate
        url = self.cvp_url_prefix + '/web/login/authenticate.do'
        authdata = {'userId': cvp_username, 'password': cvp_password}
        resp = self.session.post(url, data=json.dumps(
            authdata), timeout=self.timeout)
        if resp.raise_for_status():
            sys.exit('ERROR: Received wrong status code when connecting to CVP!')

    @staticmethod
    def handle_errors(r, task_description='A request to CVP REST API'):
        # handles possible CVP or requests errors
        if isinstance(r, str):
            sys.exit('%s failed!\nERROR: %s' % (
                task_description, r
            ))
        if 'errorCode' in r.json():
            sys.exit('%s failed!\nERROR code: %s\n   message: %s' % (
                task_description, r.json()['errorCode'], r.json()[
                    'errorMessage']
            ))
        if r.raise_for_status():
            err_msg = 'ERROR: %s failed! Wrong status code %s received' % (
                task_description, r.status_code)
            sys.exit(err_msg)

    def get_configlets(self):
        url = self.cvp_url_prefix + \
            '/cvpservice/configlet/getConfiglets.do?startIndex=0&endIndex=0'
        resp = self.session.get(url, timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Collecting configlet inventory')
        d = dict()
        for configlet in resp.json()['data']:
            d.update({
                configlet['key']: configlet
            })
        return d

    def get_devices(self, provisioned=False):
        # provisioned: True - provisioned only, False - full inventory, including Undefined container
        url = self.cvp_url_prefix + '/cvpservice/inventory/devices?provisioned=%s' % provisioned
        resp = self.session.get(url, timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Collecting device inventory')
        d = dict()
        for device in resp.json():
            d.update({
                device['serialNumber']: device
            })
        return d

    def get_containers(self):
        url = self.cvp_url_prefix + '/cvpservice/inventory/containers'
        resp = self.session.get(url, timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Collecting container inventory')
        d = dict()
        for container in resp.json():
            d.update({
                container['Key']: container
            })
        return d

    def find_container_id(self, container_name):
        container_inventory = self.get_containers()
        for container_key, container_details in container_inventory.items():
            if container_details['Name'] == container_name:
                return container_key

    def find_builder_id(self, builder_name):
        configlet_inventory = self.get_configlets()
        for cfglet_id, cfglet_details in configlet_inventory.items():
            if (cfglet_details['name'] == builder_name) and (cfglet_details['type'] == 'Builder'):
                return cfglet_id

    def get_device_serials_in_container(self, container_key):
        url = self.cvp_url_prefix + \
            '/cvpservice/provisioning/getNetElementList.do?nodeId=%s&startIndex=0&endIndex=0&ignoreAdd=true' % container_key
        resp = self.session.get(url, timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Collecting devices in a container')
        d = dict()
        for device in resp.json()['netElementList']:
            d.update({
                device['serialNumber']: device
            })
        return d

    def generate_configlets_from_builder(self, builder_key, netelement_key_list, container_key):
        url = self.cvp_url_prefix + '/cvpservice/configlet/autoConfigletGenerator.do'
        payload = {
            'configletBuilderId': builder_key,
            'netElementIds': netelement_key_list,
            'containerId': container_key,
            'pageType': 'string'
        }
        resp = self.session.post(
            url, data=json.dumps(payload), timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Generating updated configlets from builder')
        return resp.json()

    def get_configlets_for_a_device(self, netelement_id):
        url = self.cvp_url_prefix + \
            '/cvpservice/provisioning/getConfigletsByNetElementId.do?netElementId=%s&startIndex=0&endIndex=0' % netelement_id
        resp = self.session.get(url, timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Collecting container inventory')
        assigned_configlet_list = resp.json()['configletList']
        return assigned_configlet_list

    def addTempTask(self, temp_task_data, info=''):
        # used to format and add new task to the temp task list
        taskId = len(self.temp_task_list) + 1
        d = {
            "taskId": taskId,
            "info": info,
            "infoPreview": info,
        }
        d.update(temp_task_data)
        self.temp_task_list.append(d)

        return d

    def reassign_configlets_to_device(self, device, configlet_list_to_unassign, configlet_list_to_assign):

        info = "Reassigning configlets to device %s" % device_details['serialNumber']

        c_names_to_remove = list()
        c_keys_to_remove = list()
        b_names_to_remove = list()
        b_keys_to_remove = list()
        c_names_to_add = list()
        c_keys_to_add = list()
        b_names_to_add = list()
        b_keys_to_add = list()

        for cfglet in configlet_list_to_unassign:
            if cfglet['type'] == 'Builder':
                b_names_to_remove.append(cfglet['name'])
                b_keys_to_remove.append(cfglet['key'])
            else:
                c_names_to_remove.append(cfglet['name'])
                c_keys_to_remove.append(cfglet['key'])

        for cfglet in configlet_list_to_assign:
            if cfglet['type'] == 'Builder':
                b_names_to_add.append(cfglet['name'])
                b_keys_to_add.append(cfglet['key'])
            else:
                c_names_to_add.append(cfglet['name'])
                c_keys_to_add.append(cfglet['key'])

        task_d = {
            'action': 'associate',
            'nodeType': 'configlet',
            'nodeId': '',
            'configletList': c_keys_to_add,
            'configletNamesList': c_names_to_add,
            'ignoreConfigletNamesList': c_names_to_remove,
            'ignoreConfigletList': c_keys_to_remove,
            'configletBuilderList': b_keys_to_add,
            'configletBuilderNamesList': b_names_to_add,
            'ignoreConfigletBuilderList': b_keys_to_remove,
            'ignoreConfigletBuilderNamesList': b_names_to_remove,
            'toId': device['systemMacAddress'],
            'toIdType': 'netelement',
            'fromId': '',
            'nodeName': '',
            'fromName': '',
            'toName': device['fqdn'],
            'nodeIpAddress': device['ipAddress'],
            # test with IP address change
            'nodeTargetIpAddress': device['ipAddress'],
            'childTasks': [],
            'parentTask': ''
        }
        self.addTempTask(task_d, info)

    def addTempAction(self):
        if len(self.temp_task_list):
            url = self.cvp_url_prefix + \
                '/cvpservice/provisioning/addTempAction.do?nodeId=root&format=topology'
            payload = {'data': self.temp_task_list}
            headers = {'content-type': "application/json", }
            resp = self.session.post(url, data=json.dumps(
                payload), headers=headers, timeout=self.timeout)
            self.handle_errors(
                resp, task_description='Trying to add temp tasks to CVP')
            self.temp_task_list = list()  # clean temp task list

    def save_topology(self):
        url = self.cvp_url_prefix + '/cvpservice/provisioning/v2/saveTopology.do'
        resp = self.session.post(
            url, data=json.dumps([]), timeout=self.timeout)
        self.handle_errors(resp, task_description='Saving topology')

    def delete_configlets(self, configlet_list):
        url = self.cvp_url_prefix + '/cvpservice/configlet/deleteConfiglet.do'
        configlets_to_delete = list()
        for configlet in configlet_list:
            d = {'name': configlet['name'], 'key': configlet['key']}
            configlets_to_delete.append(d)
        resp = self.session.post(url, data=json.dumps(
            configlets_to_delete), timeout=self.timeout)
        self.handle_errors(resp, task_description='Deleting configlets')

    def get_tasks(self, query_param='Pending'):
        url = self.cvp_url_prefix + \
            '/cvpservice/task/getTasks.do?queryparam=%s&startIndex=0&endIndex=0' % query_param
        resp = self.session.get(url, timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Checking for existing tasks.')

        d = {
            'total': resp.json()['total'],
            'data': resp.json()['data']
        }

        return d

    def execute_tasks(self, task_id_list):
        url = self.cvp_url_prefix + '/cvpservice/task/executeTask.do'
        payload = {'data': task_id_list}
        headers = {'content-type': "application/json", }
        resp = self.session.post(url, data=json.dumps(
            payload), headers=headers, timeout=self.timeout)
        self.handle_errors(
            resp, task_description='Trying to add temp tasks to CVP')

    def device_is_compliant(self, device_id):
        url = self.cvp_url_prefix + '/cvpservice/provisioning/checkCompliance.do'
        d = {'nodeId': device_id, 'nodeType': 'netelement'}
        resp = self.session.post(url, data=json.dumps(d), timeout=self.timeout)
        self.handle_errors(resp, task_description='Deleting configlets')
        if resp.json()['complianceCode'] != '0000':
            return False  # not compliant
        else:
            return True  # compliant


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)

    cli_parser_description = (
        "Multicast Auto Reconcile Configlet Builder\n"
        "This Python code must be used as configlet builder on CVP\n"
        "It helps to reconcile the config produced by M&E controller (multicast routes) automatically.\n"
        "This builder can be triggered before executing the change by trigger-mcast-reconcile.py\n"
    )

    parser = argparse.ArgumentParser(
        description=cli_parser_description, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('--cvp', dest='cvp_ip_or_name',
                        required=True, help='CVP IP address or DNS name.')
    parser.add_argument('--username', '-user', dest='cvp_username',
                        required=True, help='CVP username.')
    args = parser.parse_args()

    # get password to authenticate on CVP
    cvp_password = getpass.getpass(prompt='Password:')

    logging.info(f'Connecting to https://{args.cvp_ip_or_name}')
    cvp_api = CVP(url_prefix=f'https://{args.cvp_ip_or_name}',
                  cvp_username=args.cvp_username, cvp_password=cvp_password)

    # map builder keys to device parent container and system MACs
    builder_device_map = dict()
    # { 'cfglet_builder_key': { 'parentContainerKey': [ 'systemMacAddress', ... ], ... }, ... }
    builder_names = list()  # list of configlet builder names
    device_dict = dict()  # dictionary to store device details for every system MAC
    device_sys_mac_to_configlet_map = dict()  # assigned configlets for every system MAC to avoid additional API calls

    # get device inventory and walk over it
    logging.info('Collecting device inventory.')
    device_inventory = cvp_api.get_devices()
    for k, v in device_inventory.items():  # k - device serial, v - device details data
        # find configlets assigned to every device
        logging.info(f"Find configlets assigned to {v['systemMacAddress']}")
        configlets_assigned_to_device = cvp_api.get_configlets_for_a_device(
            v['systemMacAddress'])
        device_sys_mac_to_configlet_map.update({
            v['systemMacAddress']: configlets_assigned_to_device
        })
        for cfglet in configlets_assigned_to_device:
            # for every builder add information about device system MAC and parent container to builder_device_map
            if cfglet['type'] == 'Builder':
                builder_names.append(cfglet['name'])
                # add device to the dict first
                device_dict.update({v['systemMacAddress']: v})
                if cfglet['key'] not in builder_device_map.keys():
                    builder_device_map.update({
                        cfglet['key']: dict()
                    })
                if v['parentContainerKey'] not in builder_device_map[cfglet['key']].keys():
                    builder_device_map[cfglet['key']].update({
                        v['parentContainerKey']: list()
                    })
                if v['systemMacAddress'] not in builder_device_map[cfglet['key']][v['parentContainerKey']]:
                    builder_device_map[cfglet['key']][v['parentContainerKey']].append(
                        v['systemMacAddress'])

    # here we'll add all configlets that are not in use after the change
    configlets_to_be_deleted = list()
    for builder_id, cont_device_bundle in builder_device_map.items():
        for container_id, device_list in cont_device_bundle.items():
            # use confilet builder to generate new configlets for every device in the list
            logging.info(
                f'Generating configlets from builder {builder_id} for devices {device_list} in container {container_id}')
            new_configlets = cvp_api.generate_configlets_from_builder(
                builder_id, device_list, container_id)['data']

            for device_id in device_list:

                change_detected = False  # but default we assume that there is no change

                device_details = device_dict[device_id]
                configlets_to_be_assigned = list()  # configlets to be assigned to the device
                # configlets to be unassigned from the device
                configlets_to_be_unassigned = list()

                # lists below are used to verify that no generated configlets will be lost
                gen_cfglet_prefixes_already_assigned_to_device = list()
                gen_cfglet_prefixes_expected_to_be_assigned_to_device = list()

                configlets_assigned_to_device = device_sys_mac_to_configlet_map[device_details['systemMacAddress']]
                for configlet in configlets_assigned_to_device:
                    # for every builder we expect a generated configlet to be assigned to a device
                    # in some cases generated configlets can be removed by operator by mistake and lost
                    # to recover from that, we add every builder name to the list of generated configlet prefixes expected to be assigned to the device
                    # if we'll find a matching generated configlet, this prefix will be removed from the list
                    # otherwise we'll recreate corresponding generated configlets
                    if configlet['type'] == 'Builder':
                        # if no matching generated configlet discovered yet
                        if configlet['name'] not in gen_cfglet_prefixes_already_assigned_to_device:
                            gen_cfglet_prefixes_expected_to_be_assigned_to_device.append(
                                configlet['name'])
                    # if configlet is generated, find the name of the corresponding configlet builder
                    builder_name = ''
                    if configlet['type'] == 'Generated':
                        for candidate_builder_name in builder_names:
                            if candidate_builder_name in configlet['name']:
                                builder_name = candidate_builder_name
                                # find generated configlet name prefix
                                # for example for mcast_auto_reconcile_192.168.122.11_5 the prefix will be mcast_auto_reconcile_192.168.122.11
                                existing_cfglet_name_without_version = configlet['name'][:configlet['name'].rfind(
                                    '_')]
                                # find new generated configlets for the builder
                                for new_configlet_data in new_configlets:
                                    new_cfglet = new_configlet_data['configlet']
                                    # find generated configlet name prefix for the updated configlet
                                    new_cfglet_name_without_version = new_cfglet['name'][:new_cfglet['name'].rfind(
                                        '_')]
                                    if existing_cfglet_name_without_version == new_cfglet_name_without_version:
                                        # if generated configlet was not changed
                                        if configlet['key'] == new_cfglet['key']:
                                            configlets_to_be_assigned.append(
                                                configlet)  # keep old configlet
                                        else:
                                            # check if config has changed
                                            if configlet['config'] != new_cfglet['config']:
                                                logging.info(f"A change was detected. {configlet['name']} will be replaced with {new_cfglet['name']}")
                                                change_detected = True
                                                configlets_to_be_assigned.append(
                                                    new_cfglet)  # assign new configlet
                                                configlets_to_be_unassigned.append(
                                                    configlet)  # unassign old configlet
                                                configlets_to_be_deleted.append(
                                                    configlet)  # delete old configlet
                                        # add builder to the list of already assigned prefixes as generated configlet was discovered
                                        gen_cfglet_prefixes_already_assigned_to_device.append(
                                            builder_name)
                                        # remove builder name from the list of generated configlet prefixes expected to be assigned to the device
                                        if builder_name in gen_cfglet_prefixes_expected_to_be_assigned_to_device:
                                            gen_cfglet_prefixes_expected_to_be_assigned_to_device.remove(
                                                builder_name)
                    else:  # just keep configlets of any other type
                        configlets_to_be_assigned.append(configlet)

                # if any lost generated configlets discovered
                for lost_configlet_prefix in gen_cfglet_prefixes_expected_to_be_assigned_to_device:
                    # first, find builder index as configlet has to be inserted right after
                    for cfglet_index, to_be_assigned_cfglet in enumerate(configlets_to_be_assigned):
                        if to_be_assigned_cfglet['name'] == lost_configlet_prefix:
                            lost_configlet_index = cfglet_index
                            for new_configlet_data in new_configlets:
                                new_cfglet = new_configlet_data['configlet']
                                if lost_configlet_prefix in new_cfglet['name']:
                                    configlets_to_be_assigned.insert(
                                        lost_configlet_index+1, new_cfglet)
                                    logging.info(f"Recovering configlet {new_cfglet['name']} that was lost due to operator error.")
                                    change_detected = True

                # typically we'd check if device is compliant,
                # but it will never be the case due to custom TerminAttr
                # keep the code below commented just in case it will be required later
                # --------------------------------------------------------------------
                # if not change_detected:
                #     if not cvp_api.device_is_compliant(device_id):
                #         change_detected = True

                if change_detected:
                    logging.info(f"Re-assigning configlets to {device_details['systemMacAddress']}")
                    cvp_api.reassign_configlets_to_device(
                        device_details, configlets_to_be_unassigned, configlets_to_be_assigned)
                    logging.info("Adding temp actions and saving topology.")
                    cvp_api.addTempAction()  # create temp actions on CVP
                    cvp_api.save_topology()  # save topology
                else:
                    logging.info('No change was detected. Nothing to do.')

    if configlets_to_be_deleted:
        logging.info('Deleting configlets that are no longer required.')
        cvp_api.delete_configlets(configlets_to_be_deleted)
