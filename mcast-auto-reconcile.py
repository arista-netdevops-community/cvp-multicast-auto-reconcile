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

"""Multicast Auto Reconcile Configlet Builder
This Python code must be used as configlet builder on CVP
It helps to reconcile the config produced by M&E controller (multicast routes) automatically.
This builder can be triggered before executing the change by trigger-mcast-reconcile.py
"""

__author__ = 'Petr Ankudinov'

from cvplibrary import CVPGlobalVariables, GlobalVariableNames, Device
from time import time

# find device IP
device_ip = CVPGlobalVariables.getValue(GlobalVariableNames.CVP_IP)
device_serial = CVPGlobalVariables.getValue(GlobalVariableNames.CVP_SERIAL)
# find username and password
ztp = CVPGlobalVariables.getValue(GlobalVariableNames.ZTP_STATE)
if ztp == 'true':
    user = CVPGlobalVariables.getValue(GlobalVariableNames.ZTP_USERNAME)
    passwd = CVPGlobalVariables.getValue(GlobalVariableNames.ZTP_PASSWORD)
else:
    user = CVPGlobalVariables.getValue(GlobalVariableNames.CVP_USERNAME)
    passwd = CVPGlobalVariables.getValue(GlobalVariableNames.CVP_PASSWORD)
    
device = Device(device_ip, username=user, password=passwd)
cmdList = ['enable', 'show running-config']
# get `router multicast` config section
mcast_config = device.runCmds(cmdList)[1]['response']['cmds']['router multicast']['cmds']['ipv4']['cmds'].keys()
# re-build multicast config from the device running config
print('router multicast')
print('   ipv4')
for line in mcast_config:
  print(' '*6+line)
