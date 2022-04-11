from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, call

import asynctest
import resources_aiotransmission as rsrc

from stig.client import ClientError
from stig.client.aiotransmission.api_settings import SettingsAPI
from stig.client.utils import Bandwidth, Bool, Int, Path, const, convert


class FakeTransmissionRPC():
    connected = True

    def __init__(self, *args, **kwargs):
        self.fake_settings = deepcopy(rsrc.SESSION_GET_RESPONSE['arguments'])

    async def session_get(self):
        return self.fake_settings

    async def session_set(self, settings):
        self.fake_settings.update(settings)


class TestSettingsAPI(asynctest.TestCase):
    async def setUp(self):
        self.rpc = FakeTransmissionRPC()
        srvapi = SimpleNamespace(rpc=self.rpc)
        self.api = SettingsAPI(srvapi)


    async def test_attrs_have_corresponding_methods(self):
        for name in self.api:
            getter = 'get_' + name.replace('.', '_')
            self.assertTrue(hasattr(self.api, getter))
            setter = 'get_' + name.replace('.', '_')
            self.assertTrue(hasattr(self.api, setter))

    async def test_description(self):
        for name in self.api:
            desc = self.api.description(name)
            self.assertIsInstance(desc, str)
            self.assertTrue('\n' not in desc)

    async def test_syntax(self):
        for name in self.api:
            syntax = self.api.syntax(name)
            self.assertIsInstance(syntax, str)

    async def test_rpc_unreachable(self):
        class UnreachableRPC(FakeTransmissionRPC):
            async def session_get(self):
                raise ClientError('Something went wrong.')

            async def session_set(self, settings):
                raise ClientError('Nah.')

        self.rpc = UnreachableRPC()
        self.api = SettingsAPI(SimpleNamespace(rpc=self.rpc))
        self.rpc.fake_settings = {}
        self.rpc.fake_settings['foo'] = 'bar'

        self.assertIs(self.api['pex'], const.DISCONNECTED)
        with self.assertRaises(ClientError):
            await self.api.get_pex()

        with self.assertRaises(ClientError):
            await self.api.set_pex(True)

    async def test_get_method(self):
        self.rpc.fake_settings['alt-speed-up'] = 500
        self.rpc.fake_settings['alt-speed-enabled'] = True
        self.assertEqual(await self.api.get('limit.rate.alt.up'), 500e3)
        with self.assertRaises(ValueError):
            await self.api.get('foo')

    async def test_set_method(self):
        # We need a spec from a callable because blinker does some weird stuff and we get
        # an AttributeError for '__self__' without the spec.
        cb_any = Mock(spec=lambda self: None)
        self.api.on_set(cb_any)
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='limit.rate.down')

        await self.api.set('limit.rate.down', 555e3)

        self.assertEqual(self.rpc.fake_settings['speed-limit-down'], 555)
        self.assertEqual(self.rpc.fake_settings['speed-limit-down-enabled'], True)

        cb_any.assert_called_once_with(self.api)
        cb.assert_called_once_with(self.api)

        with self.assertRaises(ValueError):
            await self.api.set('foo', 'bar')


    async def test_get_autostart(self):
        self.assertIs(self.api['autostart'], const.DISCONNECTED)

        self.rpc.fake_settings['start-added-torrents'] = True
        value = await self.api.get_autostart()
        self.assertIsInstance(value, Bool)
        self.assertTrue(value)
        self.assertIs(self.api['autostart'], value)

        self.rpc.fake_settings['start-added-torrents'] = False
        self.assertTrue(self.api['autostart'])  # Old value from cache
        value = await self.api.get_autostart()
        self.assertIsInstance(value, Bool)
        self.assertFalse(value)
        self.assertIs(self.api['autostart'], value)

    async def test_set_autostart(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='autostart')

        await self.api.set_autostart(True)
        self.assertEqual(self.rpc.fake_settings['start-added-torrents'], True)
        await self.api.set_autostart(False)
        self.assertEqual(self.rpc.fake_settings['start-added-torrents'], False)
        with self.assertRaises(ValueError):
            await self.api.set_autostart('hello?')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_port(self):
        self.assertEqual(self.api['port'], const.DISCONNECTED)

        self.rpc.fake_settings['peer-port'] = 1234
        value = await self.api.get_port()
        self.assertIsInstance(value, Int)
        self.assertEqual(value, 1234)
        self.assertEqual(str(value), '1234')
        self.assertIs(self.api['port'], value)

    async def test_set_port(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='port')

        self.rpc.fake_settings['peer-port'] = 123
        await self.api.set_port(456)
        self.assertEqual(self.rpc.fake_settings['peer-port'], 456)
        with self.assertRaises(ValueError):
            await self.api.set_port('Pick one!')

        self.assertEqual(cb.call_args_list, [call(self.api)])


    async def test_get_port_random(self):
        self.assertEqual(self.api['port.random'], const.DISCONNECTED)

        self.rpc.fake_settings['peer-port-random-on-start'] = False

        value = await self.api.get_port_random()
        self.assertIsInstance(value, Bool)
        self.assertFalse(value)
        self.assertIs(self.api['port.random'], value)

    async def test_set_port_random(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='port.random')

        self.rpc.fake_settings['peer-port-random-on-start'] = True

        await self.api.set_port_random(False)
        self.assertEqual(self.rpc.fake_settings['peer-port-random-on-start'], False)

        await self.api.set_port_random('yes')
        self.assertEqual(self.rpc.fake_settings['peer-port-random-on-start'], True)

        with self.assertRaises(ValueError):
            await self.api.set_port_random('For sure!')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_port_forwarding(self):
        self.rpc.fake_settings['port-forwarding-enabled'] = True
        value = await self.api.get_port_forwarding()
        self.assertIsInstance(value, Bool)
        self.assertTrue(value)

        self.rpc.fake_settings['port-forwarding-enabled'] = False
        value = await self.api.get_port_forwarding()
        self.assertIsInstance(value, Bool)
        self.assertFalse(value)

    async def test_set_port_forwarding(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='port.forwarding')

        self.rpc.fake_settings['port-forwarding-enabled'] = False

        await self.api.set_port_forwarding('on')
        self.assertEqual(self.rpc.fake_settings['port-forwarding-enabled'], True)

        await self.api.set_port_forwarding('no')
        self.assertEqual(self.rpc.fake_settings['port-forwarding-enabled'], False)

        with self.assertRaises(ValueError):
            await self.api.set_port_forwarding('over my dead body')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_limit_peers_global(self):
        self.assertIs(self.api['limit.peers.global'], const.DISCONNECTED)

        self.rpc.fake_settings['peer-limit-global'] = 17
        value = await self.api.get_limit_peers_global()
        self.assertIsInstance(value, Int)
        self.assertEqual(value, 17)

        self.rpc.fake_settings['peer-limit-global'] = 17000
        value = await self.api.get_limit_peers_global()
        self.assertIsInstance(value, Int)
        self.assertEqual(value, 17000)
        self.assertEqual(str(value), '17k')

    async def test_set_limit_peers_global(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='limit.peers.global')

        self.assertIs(self.api['limit.peers.global'], const.DISCONNECTED)

        self.assertNotEqual(self.rpc.fake_settings['peer-limit-global'], 58329)
        await self.api.set_limit_peers_global(58329)
        self.assertEqual(self.rpc.fake_settings['peer-limit-global'], 58329)

        await self.api.set_limit_peers_global('10k')
        self.assertEqual(self.rpc.fake_settings['peer-limit-global'], 10000)

        with self.assertRaises(ValueError):
            await self.api.set_limit_peers_global('all of them')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_limit_peers_torrent(self):
        self.assertIs(self.api['limit.peers.torrent'], const.DISCONNECTED)

        self.rpc.fake_settings['peer-limit-per-torrent'] = 17
        value = await self.api.get_limit_peers_torrent()
        self.assertIsInstance(value, Int)
        self.assertEqual(value, 17)

        self.rpc.fake_settings['peer-limit-per-torrent'] = 17000
        value = await self.api.get_limit_peers_torrent()
        self.assertIsInstance(value, Int)
        self.assertEqual(value, 17000)
        self.assertEqual(str(value), '17k')

    async def test_set_limit_peers_torrent(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='limit.peers.torrent')

        self.assertIs(self.api['limit.peers.torrent'], const.DISCONNECTED)

        self.assertNotEqual(self.rpc.fake_settings['peer-limit-per-torrent'], 58329)
        await self.api.set_limit_peers_torrent(58329)
        self.assertEqual(self.rpc.fake_settings['peer-limit-per-torrent'], 58329)

        await self.api.set_limit_peers_torrent('10.1k')
        self.assertEqual(self.rpc.fake_settings['peer-limit-per-torrent'], 10100)

        with self.assertRaises(ValueError):
            await self.api.set_limit_peers_global('all of them')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_encryption(self):
        self.assertEqual(self.api['encryption'], const.DISCONNECTED)

        self.rpc.fake_settings['encryption'] = 'tolerated'
        value = await self.api.get_encryption()
        self.assertEqual(value, 'tolerated')
        self.assertIs(self.api['encryption'], value)

        self.rpc.fake_settings['encryption'] = 'preferred'
        value = await self.api.get_encryption()
        self.assertEqual(value, 'preferred')
        self.assertIs(self.api['encryption'], value)

        self.rpc.fake_settings['encryption'] = 'required'
        value = await self.api.get_encryption()
        self.assertEqual(value, 'required')
        self.assertIs(self.api['encryption'], value)

    async def test_set_encryption(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='encryption')

        self.rpc.fake_settings['encryption'] = 'required'
        await self.api.set_encryption('preferred')
        self.assertEqual(self.rpc.fake_settings['encryption'], 'preferred')
        await self.api.set_encryption('tolerated')
        self.assertEqual(self.rpc.fake_settings['encryption'], 'tolerated')
        await self.api.set_encryption('required')
        self.assertEqual(self.rpc.fake_settings['encryption'], 'required')
        with self.assertRaises(ValueError):
            await self.api.set_encryption('AES256')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api), call(self.api)])


    async def test_get_utp(self):
        self.assertEqual(self.api['utp'], const.DISCONNECTED)

        self.rpc.fake_settings['utp-enabled'] = True
        value = await self.api.get_utp()
        self.assertIsInstance(value, Bool)
        self.assertTrue(value)
        self.assertIs(self.api['utp'], value)

        self.rpc.fake_settings['utp-enabled'] = False
        value = await self.api.get_utp()
        self.assertIsInstance(value, Bool)
        self.assertFalse(value)
        self.assertIs(self.api['utp'], value)

    async def test_set_utp(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='utp')

        await self.api.set_utp(True)
        self.assertEqual(self.rpc.fake_settings['utp-enabled'], True)
        await self.api.set_utp(False)
        self.assertEqual(self.rpc.fake_settings['utp-enabled'], False)
        with self.assertRaises(ValueError):
            await self.api.set_utp('a fishy value')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_dht(self):
        self.assertEqual(self.api['dht'], const.DISCONNECTED)

        self.rpc.fake_settings['dht-enabled'] = True
        value = await self.api.get_dht()
        self.assertIsInstance(value, Bool)
        self.assertTrue(value)
        self.assertIs(self.api['dht'], value)

        self.rpc.fake_settings['dht-enabled'] = False
        value = await self.api.get_dht()
        self.assertIsInstance(value, Bool)
        self.assertFalse(value)
        self.assertIs(self.api['dht'], value)

    async def test_set_dht(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='dht')

        await self.api.set_dht(True)
        self.assertEqual(self.rpc.fake_settings['dht-enabled'], True)
        await self.api.set_dht(False)
        self.assertEqual(self.rpc.fake_settings['dht-enabled'], False)
        with self.assertRaises(ValueError):
            await self.api.set_dht('not a boolean')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_pex(self):
        self.assertEqual(self.api['pex'], const.DISCONNECTED)

        self.rpc.fake_settings['pex-enabled'] = True
        value = await self.api.get_pex()
        self.assertIsInstance(value, Bool)
        self.assertTrue(value)
        self.assertIs(self.api['pex'], value)

        self.rpc.fake_settings['pex-enabled'] = False
        value = await self.api.get_pex()
        self.assertIsInstance(value, Bool)
        self.assertFalse(value)
        self.assertIs(self.api['pex'], value)

    async def test_set_pex(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='pex')

        await self.api.set_pex(True)
        self.assertEqual(self.rpc.fake_settings['pex-enabled'], True)
        await self.api.set_pex(False)
        self.assertEqual(self.rpc.fake_settings['pex-enabled'], False)
        with self.assertRaises(ValueError):
            await self.api.set_pex('not a boolean')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_lpd(self):
        self.assertEqual(self.api['lpd'], const.DISCONNECTED)

        self.rpc.fake_settings['lpd-enabled'] = True
        value = await self.api.get_lpd()
        self.assertIsInstance(value, Bool)
        self.assertTrue(value)
        self.assertIs(self.api['lpd'], value)

        self.rpc.fake_settings['lpd-enabled'] = False
        value = await self.api.get_lpd()
        self.assertIsInstance(value, Bool)
        self.assertFalse(value)
        self.assertIs(self.api['lpd'], value)

    async def test_set_lpd(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='lpd')

        await self.api.set_lpd(True)
        self.assertEqual(self.rpc.fake_settings['lpd-enabled'], True)
        await self.api.set_lpd(False)
        self.assertEqual(self.rpc.fake_settings['lpd-enabled'], False)
        with self.assertRaises(ValueError):
            await self.api.set_lpd('One ValueError, please.')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_path_complete(self):
        self.assertEqual(self.api['path.complete'], const.DISCONNECTED)

        self.rpc.fake_settings['download-dir'] = '/foo/bar'
        value = await self.api.get_path_complete()
        self.assertIsInstance(value, Path)
        self.assertEqual(value, '/foo/bar')

    async def test_set_path_complete(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='path.complete')

        self.rpc.fake_settings['download-dir'] = '/foo/bar'
        await self.api.set_path_complete('/bar/baz')
        self.assertEqual(self.rpc.fake_settings['download-dir'], '/bar/baz')

        await self.api.set_path_complete('blam')
        self.assertEqual(self.rpc.fake_settings['download-dir'], '/bar/baz/blam')

        await self.api.set_path_complete('////bli/bloop///di/blop//')
        self.assertEqual(self.rpc.fake_settings['download-dir'], '/bli/bloop/di/blop')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api), call(self.api)])


    async def test_get_path_incomplete(self):
        self.assertEqual(self.api['path.incomplete'], const.DISCONNECTED)

        self.rpc.fake_settings['incomplete-dir-enabled'] = True
        self.rpc.fake_settings['incomplete-dir'] = '/fim/fam'
        value = await self.api.get_path_incomplete()
        self.assertIsInstance(value, Path)
        self.assertEqual(value, '/fim/fam')

        self.rpc.fake_settings['incomplete-dir-enabled'] = False
        value = await self.api.get_path_incomplete()
        self.assertIsInstance(value, Bool)
        self.assertEqual(value, False)


    async def test_set_path_incomplete(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='path.incomplete')

        self.rpc.fake_settings['incomplete-dir-enabled'] = False
        self.rpc.fake_settings['incomplete-dir'] = '/foo'

        await self.api.set_path_incomplete('/baa/boo')
        self.assertEqual(self.rpc.fake_settings['incomplete-dir-enabled'], True)
        self.assertEqual(self.rpc.fake_settings['incomplete-dir'], '/baa/boo')

        await self.api.set_path_incomplete(False)
        self.assertEqual(self.rpc.fake_settings['incomplete-dir-enabled'], False)
        self.assertEqual(self.rpc.fake_settings['incomplete-dir'], '/baa/boo')

        await self.api.set_path_incomplete(True)
        self.assertEqual(self.rpc.fake_settings['incomplete-dir-enabled'], True)
        self.assertEqual(self.rpc.fake_settings['incomplete-dir'], '/baa/boo')

        await self.api.set_path_incomplete('relative///path//')
        self.assertEqual(self.rpc.fake_settings['incomplete-dir-enabled'], True)
        self.assertEqual(self.rpc.fake_settings['incomplete-dir'], '/baa/boo/relative/path')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api), call(self.api), call(self.api)])


    async def test_get_files_part(self):
        self.assertEqual(self.api['files.part'], const.DISCONNECTED)

        self.rpc.fake_settings['rename-partial-files'] = False
        value = await self.api.get_files_part()
        self.assertIsInstance(value, Bool)
        self.assertEqual(value, False)

        self.rpc.fake_settings['rename-partial-files'] = True
        value = await self.api.get_files_part()
        self.assertIsInstance(value, Bool)
        self.assertEqual(value, True)

    async def test_set_files_part(self):
        cb = Mock(spec=lambda self: None)
        self.api.on_set(cb, key='files.part')

        self.rpc.fake_settings['rename-partial-files'] = False
        await self.api.set_files_part(True)
        self.assertEqual(self.rpc.fake_settings['rename-partial-files'], True)

        await self.api.set_files_part(False)
        self.assertEqual(self.rpc.fake_settings['rename-partial-files'], False)

        with self.assertRaises(ValueError):
            await self.api.set_files_part('foo')

        self.assertEqual(cb.call_args_list, [call(self.api), call(self.api)])


    async def test_get_limit_rate(self):
        for direction in ('up', 'down'):
            convert.bandwidth.unit = 'byte'
            self.api.clearcache()

            method = getattr(self.api, 'get_limit_rate_' + direction)
            value_field = 'speed-limit-' + direction
            enabled_field = 'speed-limit-' + direction + '-enabled'
            key = 'limit.rate.' + direction

            self.assertEqual(self.api[key], const.DISCONNECTED)

            self.rpc.fake_settings[enabled_field] = False
            value = await method()
            self.assertIs(value, const.UNLIMITED)
            self.assertTrue(value >= float('inf'))
            self.assertEqual(str(value), 'unlimited')

            self.rpc.fake_settings[enabled_field] = True
            self.rpc.fake_settings[value_field] = 100
            value = await method()
            self.assertIsInstance(value, Bandwidth)
            self.assertEqual(value, 100e3)
            self.assertEqual(str(value), '100kB')

            convert.bandwidth.unit = 'bit'
            value = await method()
            self.assertIsInstance(value, Bandwidth)
            self.assertEqual(value, 800e3)
            self.assertEqual(str(value), '800kb')

    async def test_set_limit_rate(self):
        for direction in ('up', 'down'):
            cb = Mock(spec=lambda self: None)
            self.api.on_set(cb, key='limit.rate.' + direction)
            exp_cb_calls = 0

            convert.bandwidth.unit = 'byte'

            method = getattr(self.api, 'set_limit_rate_' + direction)
            value_field = 'speed-limit-' + direction
            enabled_field = 'speed-limit-' + direction + '-enabled'

            await method(80e3)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 80)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(0)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 0)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(-1)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 0)
            self.assertEqual(self.rpc.fake_settings[enabled_field], False)

            convert.bandwidth.unit = 'bit'
            await method(80e3)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 10)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            convert.bandwidth.unit = 'byte'
            await method('100k')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(False)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], False)

            await method(True)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method('off')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], False)

            await method('on')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(const.UNLIMITED)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], False)

            self.assertEqual(cb.call_args_list, [call(self.api)] * exp_cb_calls)

    async def test_adjust_limit_rate(self):
        for direction in ('up', 'down'):
            cb = Mock(spec=lambda self: None)
            self.api.on_set(cb, key='limit.rate.' + direction)
            exp_cb_calls = 0

            convert.bandwidth.unit = 'byte'

            method = getattr(self.api, 'adjust_limit_rate_' + direction)
            value_field = 'speed-limit-' + direction
            enabled_field = 'speed-limit-' + direction + '-enabled'

            self.rpc.fake_settings[value_field] = 80
            self.rpc.fake_settings[enabled_field] = True

            await method(-30e3)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 50)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(50e3)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(-101e3)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 0)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(-1)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 0)
            self.assertEqual(self.rpc.fake_settings[enabled_field], False)

            convert.bandwidth.unit = 'bit'
            await method(800e3)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            convert.bandwidth.unit = 'byte'
            await method('400k')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 500)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method('-800kb')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 400)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            self.assertEqual(cb.call_args_list, [call(self.api)] * exp_cb_calls)

    async def test_get_limit_rate_alt(self):
        for direction in ('up', 'down'):
            convert.bandwidth.unit = 'byte'
            self.api.clearcache()

            method = getattr(self.api, 'get_limit_rate_alt_' + direction)
            value_field = 'alt-speed-' + direction
            enabled_field = 'alt-speed-enabled'
            key = 'limit.rate.alt.' + direction

            self.assertEqual(self.api[key], const.DISCONNECTED)

            self.rpc.fake_settings[value_field] = 20
            self.rpc.fake_settings[enabled_field] = False
            self.assertEqual(await method(), const.UNLIMITED)
            self.assertEqual(self.api[key], const.UNLIMITED)

            self.rpc.fake_settings[enabled_field] = True
            self.assertEqual(await method(), 20e3)
            self.assertEqual(self.api[key], 20e3)

    async def test_set_limit_rate_alt(self):
        for direction in ('up', 'down'):
            cb = Mock(spec=lambda self: None)
            self.api.on_set(cb, key='limit.rate.alt.' + direction)
            exp_cb_calls = 0

            convert.bandwidth.unit = 'byte'
            self.api.clearcache()

            method = getattr(self.api, 'set_limit_rate_alt_' + direction)
            value_field = 'alt-speed-' + direction
            enabled_field = 'alt-speed-enabled'
            key = 'limit.rate.alt.' + direction

            self.assertEqual(self.api[key], const.DISCONNECTED)

            self.rpc.fake_settings[value_field] = 1000
            self.rpc.fake_settings[enabled_field] = True
            await method('100k')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method('off')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], False)

            await method('on')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method(const.UNLIMITED)
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 100)
            self.assertEqual(self.rpc.fake_settings[enabled_field], False)

            self.assertEqual(cb.call_args_list, [call(self.api)] * exp_cb_calls)

    async def test_adjust_limit_rate_alt(self):
        for direction in ('up', 'down'):
            cb = Mock(spec=lambda self: None)
            self.api.on_set(cb, key='limit.rate.alt.' + direction)
            exp_cb_calls = 0

            convert.bandwidth.unit = 'byte'
            self.api.clearcache()

            method = getattr(self.api, 'adjust_limit_rate_alt_' + direction)
            value_field = 'alt-speed-' + direction
            enabled_field = 'alt-speed-enabled'

            self.rpc.fake_settings[value_field] = 1000
            self.rpc.fake_settings[enabled_field] = True
            await method('1000k')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 2000)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method('-500k')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 1500)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            await method('-5000k')
            exp_cb_calls += 1
            self.assertEqual(self.rpc.fake_settings[value_field], 0)
            self.assertEqual(self.rpc.fake_settings[enabled_field], True)

            self.assertEqual(cb.call_args_list, [call(self.api)] * exp_cb_calls)
