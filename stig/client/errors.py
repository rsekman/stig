# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details
# http://www.gnu.org/licenses/gpl-3.0.txt

import textwrap


class ClientError(Exception):
    def __init__(self, prefix, message=''):
        if message:
            self.prefix = str(prefix)
            self.message = str(message)
            super().__init__('%s: %s' % (self.prefix, self.message))
        else:
            self.prefix = ''
            self.message = str(prefix)
            super().__init__(self.message)

    # Making exceptions with the same arguments equal helps in the tests
    def __eq__(self, other):
        return type(self) is type(other) and self.args == other.args

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(type(self).__name__ + str(self))

class ConnectionError(ClientError):
    def __init__(self, url):
        super().__init__('Failed to connect', url)

class TimeoutError(ClientError):
    def __init__(self, timeout, url):
        super().__init__('Timeout after %ss' % (timeout,), url)

class RPCError(ClientError):
    def __init__(self, response):
        super().__init__('Invalid RPC response',
                         textwrap.shorten(response, 100, placeholder='...'))

class AuthError(ClientError):
    def __init__(self, url):
        super().__init__('Authentication failed', url)
