# Copyright (C) 2013 Samuel Damashek and Fox Wilson
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
import json
import re
import logging


def get_commands(mtype=None):
    cmds = json.load(open("commands.json"))
    if mtype is None:
        return cmds
    newcmds = []
    for i in cmds:
        if i["trigger"] == mtype:
            newcmds += [i]
    return newcmds


def mask_in_group(mask, group):
    groups = json.load(open("groups.json"))
    for i in groups[group]:
        if re.match("^%s$" % i, mask):
            return True
    return False


def channel_in_group(channel, group):
    chans = json.load(open("channels.json"))
    for i in chans[group]:
        if re.match("^%s$" % i, channel):
            return True
    return False


class BotHandler:
    def __init__(self, connection):
        self.connection = connection

    def handle(self, opts):
        mtype = opts['type']
        mdata = opts['data']
        msender = opts['sender']
        mhostmask = opts['hostmask']
        if 'channel' in opts:
            mchannel = opts['channel']
        else:
            mchannel = 'private'
        # long branchy thingy
        if mtype == 'mode':
            self.handle_mode(mdata, mchannel, msender, mhostmask)
        elif mtype == 'nick':
            self.handle_nick(mdata, mchannel, msender, mhostmask)
        elif mtype == 'message':
            self.handle_message(mdata, mchannel, msender, mhostmask)
        elif mtype == 'join':
            self.handle_join(mdata, mchannel, msender, mhostmask)
        elif mtype == 'part':
            self.handle_part(mdata, mchannel, msender, mhostmask)
        elif mtype == 'kick':
            self.handle_kick(mdata, mchannel, msender, mhostmask)

    def do_eligible(self, cmd, data, channel, sender, hostmask):
        targs = cmd["triggerargs"]
        targs["data"] = self.do_rep(None, data, targs["data"])
        x = re.match(targs["data"], data)
        if x:
            logging.debug("Trigger matches")
            if channel_in_group(channel, cmd["triggerargs"]["changroup"]):
                logging.debug("Channel matches")
                if mask_in_group(hostmask, cmd["triggerargs"]["nickgroup"]):
                    logging.debug("nick!user@host matches, running command")
                    self.do_thing(cmd["result"], {"channel": channel,
                                                  "sender": sender}, x)

    def handle_kick(self, data, channel, sender, hostmask):
        cmds = get_commands('kick')
        for i in cmds:
            self.do_eligible(i, data, channel, sender, hostmask)

    def handle_nick(self, data, channel, sender, hostmask):
        cmds = get_commands('nick')
        for i in cmds:
            logging.debug("Testing nick command %s" % i)
            self.do_eligible(i, data, channel, sender, hostmask)

    def handle_message(self, data, channel, sender, hostmask):
        cmds = get_commands('message')
        for i in cmds:
            self.do_eligible(i, data, channel, sender, hostmask)

    def handle_join(self, data, channel, sender, hostmask):
        cmds = get_commands('join')
        for i in cmds:
            self.do_eligible(i, data, channel, sender, hostmask)

    def handle_part(self, data, channel, sender, hostmask):
        cmds = get_commands('part')
        for i in cmds:
            self.do_eligible(i, data, channel, sender, hostmask)

    def handle_mode(self, data, channel, sender, hostmask):
        cmds = get_commands('mode')
        for i in cmds:
            self.do_eligible(i, data, channel, sender, hostmask)

    def do_rep(self, match, data, string):
        try:
            conf = json.load(open("config.json"))
            string = string.replace("{nick}", conf["nick"])
            string = string.replace("{sender}", data["sender"])
            string = string.replace("{chan}", data["channel"])
            groups = re.findall(r"\{g(\d+)\}", string)
            logging.debug(groups)
            for i in groups:
                try:
                    string = string.replace("{g%s}" % i, match.group(int(i)))
                    logging.debug("replacing {g%s} with %s" % (i, match.group(int(i))))
                except Exception as e:
                    logging.debug(repr(e))
        except Exception as e:
            pass
        finally:
            return string

    def do_thing(self, thing, data, trigger):
        rtype = thing["type"]
        channel = data["channel"]
        sender = data["sender"]
        if rtype == "nothing":
            return
        # Message
        if rtype == "message":
            if thing["to"] == "REPLY":
                if channel == "private":
                    cto = sender
                else:
                    cto = channel
            else:
                cto = self.do_rep(trigger, data, thing["to"])
            message = self.do_rep(trigger, data, thing["content"])
            self.connection.send_raw("PRIVMSG %s :%s" % (cto, message))
        # Nick
        if rtype == "nick":
            config = json.load(open("config.json"))
            config["nick"] = self.do_rep(trigger, data, thing["newnick"])
            f = open("config.json", "w")
            json.dump(config, f, indent=True, sort_keys=True)
            f.write("\n")
            f.close()
            self.connection.send_raw("NICK %s" % self.do_rep(trigger, data, thing["newnick"]))
        # Join
        if rtype == "join":
            thing["chan"] = self.do_rep(trigger, data, thing["chan"])
            if thing["chan"][0] != '#':
                thing["chan"] = "#%s" % thing["chan"]
            thing["chan"] = thing["chan"].split(",")[0]
            self.connection.send_raw("JOIN %s" % thing["chan"])
        # Part
        if rtype == "part":
            thing["chan"] = self.do_rep(trigger, data, thing["chan"])
            if thing["chan"][0] != '#':
                thing["chan"] = "#%s" % thing["chan"]
            thing["chan"] = thing["chan"].split(",")[0]
            self.connection.send_raw("PART %s" % thing["chan"])
        # Mode
        if rtype == "mode":
            thing["mode"] = self.do_rep(trigger, data, thing["mode"])
            thing["chan"] = self.do_rep(trigger, data, thing["chan"])
            if thing["chan"][0] != '#':
                thing["chan"] = "#%s" % thing["chan"]
            thing["chan"] = thing["chan"].split(",")[0]
            self.connection.send_raw("MODE %s %s" % (thing["chan"], thing["mode"]))
        # Kick
        if rtype == "kick":
            thing["nick"] = self.do_rep(trigger, data, thing["nick"])
            thing["chan"] = self.do_rep(trigger, data, thing["chan"])
            if thing["chan"][0] != '#':
                thing["chan"] = "#%s" % thing["chan"]
            thing["chan"] = thing["chan"].split(",")[0]
            self.connection.send_raw("KICK %s %s" % (thing["chan"], thing["nick"]))
