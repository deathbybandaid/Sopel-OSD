# coding=utf8
"""Sopel OSD

Sopel OSD is a "niche" method of displaying text in a Sopel bot
"""

# pylama:ignore=W0611


from __future__ import unicode_literals, absolute_import, division, print_function

import sopel.bot
from sopel.tools import stderr, Identifier

import time
import collections


__author__ = 'Sam Zick'
__email__ = 'sam@deathbybandaid.net'
__version__ = '0.1.0'


def configure(config):
    pass


def setup(bot):

    # Inject OSD
    stderr("[Sopel-OSD] Implanting OSD function into bot.")
    bot.osd = SopelOSD.osd
    bot.SopelWrapper.osd = SopelOSD.SopelWrapper.osd

    # overwrite default bot messaging
    stderr("[Sopel-OSD] Overwrite Default Sopel messaging commands.")
    bot.SopelWrapper.say = SopelOSD.SopelWrapper.say
    bot.SopelWrapper.action = SopelOSD.SopelWrapper.action
    bot.SopelWrapper.notice = SopelOSD.SopelWrapper.notice
    bot.SopelWrapper.reply = SopelOSD.SopelWrapper.reply


class SopelOSD:

    def osd(self, messages, recipients=None, text_method='PRIVMSG', max_messages=-1):
        """Send ``text`` as a PRIVMSG, CTCP ACTION, or NOTICE to ``recipients``.

        In the context of a triggered callable, the ``recipient`` defaults to
        the channel (or nickname, if a private message) from which the message
        was received.

        By default, unless specified in the configuration file, there is some
        built-in flood protection. Messages displayed over 5 times in 2 minutes
        will be displayed as '...'.

        The ``recipient`` can be in list format or a comma seperated string,
        with the ability to send to multiple recipients simultaneously. The
        default recipients that the bot will send to is 4 if the IRC server
        doesn't specify a limit for TARGMAX.

        Text can be sent to this function in either string or list format.
        List format will insert as small buffering space between entries in the
        list.

        There are 512 bytes available in a single IRC message. This includes
        hostmask of the bot as well as around 15 bytes of reserved IRC message
        type. This also includes the destinations/recipients of the message.
        This will split given strings/lists into a displayable format as close
        to the maximum 512 bytes as possible.

        If ``max_messages`` is given, the split mesage will display in as many
        lines specified by this argument. Specifying ``0`` or a negative number
        will display without limitation. By default this is set to ``-1`` when
        called directly. When called from the say/msg/reply/notice/action it
        will default to ``1``.
        """

        if not isinstance(messages, list):
            messages = [messages]

        text_method = text_method.upper()
        if text_method == 'SAY' or text_method not in ['NOTICE', 'ACTION']:
            text_method = 'PRIVMSG'

        if isinstance(recipients, collections.abc.KeysView):
            recipients = [x for x in recipients]

        if not isinstance(recipients, list):
            recipients = recipients.split(",")

        available_bytes = 512
        reserved_irc_bytes = 15
        available_bytes -= reserved_irc_bytes
        if not self.users or not self.users.contains(self.nick):
            hostmaskbytes = len((self.nick).encode('utf-8'))
            hostmaskbytes += 63 - hostmaskbytes
        else:
            hostmaskbytes = len((self.users.get(self.nick).hostmask).encode('utf-8'))
        available_bytes -= hostmaskbytes
        # TODO available_bytes -= len((self.hostmask).encode('utf-8'))

        maxtargets = 4
        # TODO server.capabilities.maxtargets
        recipientgroups, groupbytes = [], []
        while len(recipients):
            recipients_part = ','.join(x for x in recipients[-maxtargets:])
            groupbytes.append(len((recipients_part).encode('utf-8')))
            recipientgroups.append(recipients_part)
            del recipients[-maxtargets:]

        max_recipients_bytes = max(groupbytes)
        available_bytes -= max_recipients_bytes

        messages_refactor = ['']
        # TODO add configuration for padding amount
        message_padding = 4 * " "
        for message in messages:
            if len((messages_refactor[-1] + message_padding + message).encode('utf-8')) <= available_bytes:
                if messages_refactor[-1] == '':
                    messages_refactor[-1] = message
                else:
                    messages_refactor[-1] = messages_refactor[-1] + message_padding + message
            else:
                chunknum = 0
                chunks = message.split()
                for chunk in chunks:
                    if messages_refactor[-1] == '':
                        if len(chunk.encode('utf-8')) <= available_bytes:
                            messages_refactor[-1] = chunk
                        else:
                            chunksplit = map(''.join, zip(*[iter(chunk)] * available_bytes))
                            messages_refactor.extend(chunksplit)
                    elif len((messages_refactor[-1] + " " + chunk).encode('utf-8')) <= available_bytes:
                        if chunknum:
                            messages_refactor[-1] = messages_refactor[-1] + " " + chunk
                        else:
                            messages_refactor[-1] = messages_refactor[-1] + message_padding + chunk
                    else:
                        if len(chunk.encode('utf-8')) <= available_bytes:
                            messages_refactor.append(chunk)
                        else:
                            chunksplit = map(''.join, zip(*[iter(chunk)] * available_bytes))
                            messages_refactor.extend(chunksplit)
                    chunknum += 1

        if max_messages >= 1:
            messages_refactor = messages_refactor[:max_messages]

        for recipientgroup in recipientgroups:

            # No messages within the last 3 seconds? Go ahead!
            # Otherwise, wait so it's been at least 0.8 seconds + penalty

            recipient_id = Identifier(recipientgroup)

            recipient_stack = self.stack.setdefault(recipient_id, {
                'messages': [],
                'flood_left': 4,
                'dots': 0,
                # TODO
                # 'flood_left': self.config.core.flood_burst_lines,
            })
            recipient_stack['dots'] = 0

            for text in messages_refactor:

                try:

                    self.sending.acquire()

                    if not recipient_stack['flood_left']:
                        elapsed = time.time() - recipient_stack['messages'][-1][0]
                        # TODO
                        # recipient_stack['flood_left'] = min(
                        #    self.config.core.flood_burst_lines,
                        #    int(elapsed) * self.config.core.flood_refill_rate)
                        recipient_stack['flood_left'] = min(4, int(elapsed) * 1)

                    if not recipient_stack['flood_left']:
                        elapsed = time.time() - recipient_stack['messages'][-1][0]
                        penalty = float(max(0, len(text) - 50)) / 70
                        # TODO
                        # wait = self.config.core.flood_empty_wait + penalty
                        wait = 0.7 + penalty
                        if elapsed < wait:
                            time.sleep(wait - elapsed)

                        # Loop detection
                        messages = [m[1] for m in recipient_stack['messages'][-8:]]

                        # If what we about to send repeated at least 5 times in the
                        # last 2 minutes, replace with '...'
                        if messages.count(text) >= 5 and elapsed < 120:
                            recipient_stack['dots'] += 1
                        else:
                            recipient_stack['dots'] = 0

                    if not recipient_stack['dots'] >= 3:

                        recipient_stack['flood_left'] = max(0, recipient_stack['flood_left'] - 1)
                        recipient_stack['messages'].append((time.time(), self.safe(text)))
                        recipient_stack['messages'] = recipient_stack['messages'][-10:]

                        if recipient_stack['dots']:
                            text = '...'
                            if text_method == 'ACTION':
                                text_method = 'PRIVMSG'
                        if text_method == 'ACTION':
                            text = '\001ACTION {}\001'.format(text)
                            self.write(('PRIVMSG', recipientgroup), text)
                            text_method = 'PRIVMSG'
                        elif text_method == 'NOTICE':
                            self.write(('NOTICE', recipientgroup), text)
                        else:
                            self.write(('PRIVMSG', recipientgroup), text)

                finally:
                    self.sending.release()

    class SopelWrapper(object):

        def osd(self, messages, recipients=None, text_method='PRIVMSG', max_messages=-1):
            if recipients is None:
                recipients = self._trigger.sender
            self._bot.osd(self, messages, recipients, text_method, max_messages)

        def say(self, message, destination=None, max_messages=1):
            if destination is None:
                destination = self._trigger.sender
            self._bot.osd(self, message, destination, 'PRIVMSG', 1)
            # self._bot.say(message, destination, max_messages)

        def action(self, message, destination=None, max_messages=1):
            if destination is None:
                destination = self._trigger.sender
            self._bot.osd(self, message, destination, 'ACTION', 1)
            # self._bot.action(message, destination, max_messages)

        def notice(self, message, destination=None, max_messages=1):
            if destination is None:
                destination = self._trigger.sender
            self._bot.osd(self, message, destination, 'NOTICE', 1)
            # self._bot.notice(message, destination, max_messages)

        def reply(self, message, destination=None, reply_to=None, notice=False, max_messages=1):
            if destination is None:
                destination = self._trigger.sender
            if reply_to is None:
                reply_to = self._trigger.nick
            message = '%s: %s' % (reply_to, message)
            if notice:
                self._bot.osd(self, message, destination, 'NOTICE', 1)
            else:
                self._bot.osd(self, message, destination, 'PRIVMSG', 1)
            # self._bot.reply(message, destination, reply_to, notice, max_messages)
