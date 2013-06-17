# Copyright 2013 Openstack Foundation
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
#  under the License.

import contextlib
import mock

from oslo.config import cfg
from quantum.db import api as db_api

from quark.db import models
import quark.drivers.nvp_driver
from quark import exceptions as q_exc
from quark.tests import test_base


class TestNVPDriver(test_base.TestBase):
    def setUp(self):
        super(TestNVPDriver, self).setUp()

        if not hasattr(self, 'driver'):
            self.driver = quark.drivers.nvp_driver.NVPDriver()

        cfg.CONF.set_override('sql_connection', 'sqlite://', 'DATABASE')
        self.driver.max_ports_per_switch = 0
        db_api.configure_db()
        models.BASEV2.metadata.create_all(db_api._ENGINE)

        self.lswitch_uuid = "12345678-1234-1234-1234-123456781234"
        self.context.tenant_id = "tid"
        self.lport_uuid = "12345678-0000-0000-0000-123456781234"
        self.net_id = "12345678-1234-1234-1234-123412341234"
        self.port_id = "12345678-0000-0000-0000-123412341234"
        self.d_pkg = "quark.drivers.nvp_driver.NVPDriver"
        self.max_spanning = 3

    def _create_connection(self, switch_count=1,
                           has_switches=False, maxed_ports=False):
        connection = mock.Mock()
        lswitch = self._create_lswitch(has_switches, maxed_ports=maxed_ports)
        lswitchport = self._create_lswitch_port(self.lswitch_uuid,
                                                switch_count)
        connection.lswitch_port = mock.Mock(return_value=lswitchport)
        connection.lswitch = mock.Mock(return_value=lswitch)
        return connection

    def _create_lswitch_port(self, switch_uuid, switch_count):
        port = mock.Mock()
        port.create = mock.Mock(return_value={'uuid': self.lport_uuid})
        port_query = self._create_lport_query(switch_count)
        port.query = mock.Mock(return_value=port_query)
        port.delete = mock.Mock(return_value=None)
        return port

    def _create_lport_query(self, switch_count):
        query = mock.Mock()
        port_list = {"_relations":
                    {"LogicalSwitchConfig":
                    {"uuid": self.lswitch_uuid}}}
        port_query = {"results": [port_list], "result_count": switch_count}
        query.results = mock.Mock(return_value=port_query)
        return query

    def _create_lswitch(self, switches_available, maxed_ports):
        lswitch = mock.Mock()
        lswitch.query = mock.Mock(
            return_value=self.
            _create_lswitch_query(switches_available, maxed_ports))
        lswitch.create = mock.Mock(return_value={'uuid': self.lswitch_uuid})
        lswitch.delete = mock.Mock(return_value=None)
        return lswitch

    def _create_lswitch_query(self, switches_available, maxed_ports):
        query = mock.Mock()
        port_count = 0
        if maxed_ports:
            port_count = self.max_spanning
        lswitch_list = [{'uuid': 'abcd',
                        '_relations': {
                        'LogicalSwitchStatus': {
                        'lport_count': port_count
                        }}}]
        if not switches_available:
            lswitch_list = []
        lswitch_query = {"results": lswitch_list}
        query.relations = mock.Mock(return_value=None)
        query.results = mock.Mock(return_value=lswitch_query)
        return query

    def tearDown(self):
        db_api.clear_db()


class TestNVPDriverCreateNetwork(TestNVPDriver):
    @contextlib.contextmanager
    def _stubs(self):
        with contextlib.nested(
            mock.patch("%s.get_connection" % self.d_pkg),
        ) as (get_connection,):
            connection = self._create_connection()
            get_connection.return_value = connection
            yield connection

    def test_create_network(self):
        with self._stubs() as (connection):
            self.driver.create_network(self.context, "test")
            self.assertTrue(connection.lswitch().create.called)


class TestNVPDriverProviderNetwork(TestNVPDriver):
    """Testing all of the network types is unnecessary, but it's nice for peace
    of mind.
    """
    @contextlib.contextmanager
    def _stubs(self, tz):
        with contextlib.nested(
            mock.patch("%s.get_connection" % self.d_pkg),
        ) as (get_connection,):
            connection = self._create_connection()
            switch = self._create_lswitch(1, False)
            switch.transport_zone = mock.Mock()
            tz_results = mock.Mock()
            tz_results.results = mock.Mock(return_value=tz)
            tz_query = mock.Mock()
            tz_query.query = mock.Mock(return_value=tz_results)
            connection.transportzone = mock.Mock(return_value=tz_query)
            get_connection.return_value = connection
            yield connection, switch

    def test_config_provider_attrs_flat_net(self):
        tz = dict(result_count=1)
        with self._stubs(tz) as (connection, switch):
            self.driver._config_provider_attrs(
                connection=connection, switch=switch, phys_net="net_uuid",
                net_type="flat", segment_id=None)
            switch.transport_zone.assert_called_with(
                zone_uuid="net_uuid", transport_type="bridge", vlan_id=None)

    def test_config_provider_attrs_vlan_net(self):
        tz = dict(result_count=1)
        with self._stubs(tz) as (connection, switch):
            self.driver._config_provider_attrs(
                connection=connection, switch=switch, phys_net="net_uuid",
                net_type="vlan", segment_id=10)
            switch.transport_zone.assert_called_with(
                zone_uuid="net_uuid", transport_type="bridge", vlan_id=10)

    def test_config_provider_attrs_gre_net(self):
        tz = dict(result_count=1)
        with self._stubs(tz) as (connection, switch):
            self.driver._config_provider_attrs(
                connection=connection, switch=switch, phys_net="net_uuid",
                net_type="gre", segment_id=None)
            switch.transport_zone.assert_called_with(
                zone_uuid="net_uuid", transport_type="gre", vlan_id=None)

    def test_config_provider_attrs_stt_net(self):
        tz = dict(result_count=1)
        with self._stubs(tz) as (connection, switch):
            self.driver._config_provider_attrs(
                connection=connection, switch=switch, phys_net="net_uuid",
                net_type="stt", segment_id=None)
            switch.transport_zone.assert_called_with(
                zone_uuid="net_uuid", transport_type="stt", vlan_id=None)

    def test_config_provider_attrs_local_net(self):
        tz = dict(result_count=1)
        with self._stubs(tz) as (connection, switch):
            self.driver._config_provider_attrs(
                connection=connection, switch=switch, phys_net="net_uuid",
                net_type="local", segment_id=None)
            switch.transport_zone.assert_called_with(
                zone_uuid="net_uuid", transport_type="local", vlan_id=None)

    def test_config_provider_attrs_bridge_net(self):
        """Exists because internal driver calls can also call this method,
        and they may pass bridge in as the type as that's how it's known
        to NVP.
        """
        tz = dict(result_count=1)
        with self._stubs(tz) as (connection, switch):
            self.driver._config_provider_attrs(
                connection=connection, switch=switch, phys_net="net_uuid",
                net_type="bridge", segment_id=None)
            switch.transport_zone.assert_called_with(
                zone_uuid="net_uuid", transport_type="bridge", vlan_id=None)

    def test_config_provider_attrs_no_phys_net_or_type(self):
        with self._stubs({}) as (connection, switch):
            self.driver._config_provider_attrs(
                connection=connection, switch=switch, phys_net=None,
                net_type=None, segment_id=None)
            self.assertFalse(switch.transport_zone.called)

    def test_config_provider_attrs_vlan_net_no_segment_id_fails(self):
        with self._stubs({}) as (connection, switch):
            self.assertRaises(
                q_exc.SegmentIdRequired,
                self.driver._config_provider_attrs, connection=connection,
                switch=switch, phys_net="net_uuid", net_type="vlan",
                segment_id=None)

    def test_config_provider_attrs_non_vlan_net_with_segment_id_fails(self):
        with self._stubs({}) as (connection, switch):
            self.assertRaises(
                q_exc.SegmentIdUnsupported,
                self.driver._config_provider_attrs, connection=connection,
                switch=switch, phys_net="net_uuid", net_type="flat",
                segment_id=10)

    def test_config_phys_net_no_phys_type_fails(self):
        with self._stubs({}) as (connection, switch):
            self.assertRaises(
                q_exc.ProvidernetParamError,
                self.driver._config_provider_attrs, connection=connection,
                switch=switch, phys_net="net_uuid", net_type=None,
                segment_id=None)

    def test_config_no_phys_net_with_phys_type_fails(self):
        with self._stubs({}) as (connection, switch):
            self.assertRaises(
                q_exc.ProvidernetParamError,
                self.driver._config_provider_attrs, connection=connection,
                switch=switch, phys_net=None, net_type="flat",
                segment_id=None)

    def test_config_physical_net_doesnt_exist_fails(self):
        tz = dict(result_count=0)
        with self._stubs(tz) as (connection, switch):
            self.assertRaises(
                q_exc.PhysicalNetworkNotFound,
                self.driver._config_provider_attrs, connection=connection,
                switch=switch, phys_net="net_uuid", net_type="flat",
                segment_id=None)

    def test_config_physical_net_bad_net_type_fails(self):
        with self._stubs({}) as (connection, switch):
            self.assertRaises(
                q_exc.InvalidPhysicalNetworkType,
                self.driver._config_provider_attrs, connection=connection,
                switch=switch, phys_net="net_uuid", net_type="lol",
                segment_id=None)


class TestNVPDriverDeleteNetwork(TestNVPDriver):
    @contextlib.contextmanager
    def _stubs(self, network_exists=True):
        with contextlib.nested(
            mock.patch("%s.get_connection" % self.d_pkg),
            mock.patch("%s._lswitches_for_network" % self.d_pkg),
        ) as (get_connection, switch_list):
            connection = self._create_connection()
            get_connection.return_value = connection
            if network_exists:
                ret = {"results": [{"uuid": self.lswitch_uuid}]}
            else:
                ret = {"results": []}
            switch_list().results = mock.Mock(return_value=ret)
            yield connection

    def test_delete_network(self):
        with self._stubs() as (connection):
            self.driver.delete_network(self.context, "test")
            self.assertTrue(connection.lswitch().delete.called)

    def test_delete_network_not_exists(self):
        with self._stubs(network_exists=False) as (connection):
            self.driver.delete_network(self.context, "test")
            self.assertFalse(connection.lswitch().delete.called)


class TestNVPDriverCreatePort(TestNVPDriver):
    '''In all cases an lswitch should be queried.'''
    @contextlib.contextmanager
    def _stubs(self, has_lswitch=True, maxed_ports=False, net_details=None):
        with contextlib.nested(
            mock.patch("%s.get_connection" % self.d_pkg),
            mock.patch("%s._lswitches_for_network" % self.d_pkg),
            mock.patch("%s._get_network_details" % self.d_pkg),
        ) as (get_connection, get_switches, get_net_dets):
            connection = self._create_connection(has_switches=has_lswitch,
                                                 maxed_ports=maxed_ports)
            get_connection.return_value = connection
            get_switches.return_value = connection.lswitch().query()
            get_net_dets.return_value = net_details
            yield connection

    def test_create_port_switch_exists(self):
        with self._stubs(net_details=dict(foo=3)) as (connection):
            port = self.driver.create_port(self.context, self.net_id,
                                           self.port_id)
            self.assertTrue("uuid" in port)
            self.assertFalse(connection.lswitch().create.called)
            self.assertTrue(connection.lswitch_port().create.called)
            self.assertTrue(connection.lswitch().query.called)
            status_args, kwargs = connection.lswitch_port().\
                admin_status_enabled.call_args
            self.assertTrue(True in status_args)

    def test_create_port_switch_not_exists(self):
        with self._stubs(has_lswitch=False,
                         net_details=dict(foo=3)) as (connection):
            port = self.driver.create_port(self.context, self.net_id,
                                           self.port_id)
            self.assertTrue("uuid" in port)
            self.assertTrue(connection.lswitch().create.called)
            self.assertTrue(connection.lswitch_port().create.called)
            self.assertTrue(connection.lswitch().query.called)
            status_args, kwargs = connection.lswitch_port().\
                admin_status_enabled.call_args
            self.assertTrue(True in status_args)

    def test_create_port_no_existing_switches_fails(self):
        with self._stubs(has_lswitch=False):
            self.assertRaises(q_exc.BadNVPState, self.driver.create_port,
                              self.context, self.net_id, self.port_id, False)

    def test_create_disabled_port_switch_not_exists(self):
        with self._stubs(has_lswitch=False,
                         net_details=dict(foo=3)) as (connection):
            port = self.driver.create_port(self.context, self.net_id,
                                           self.port_id, False)
            self.assertTrue("uuid" in port)
            self.assertTrue(connection.lswitch().create.called)
            self.assertTrue(connection.lswitch_port().create.called)
            self.assertTrue(connection.lswitch().query.called)
            status_args, kwargs = connection.lswitch_port().\
                admin_status_enabled.call_args
            self.assertTrue(False in status_args)

    def test_create_port_switch_exists_spanning(self):
        with self._stubs(maxed_ports=True,
                         net_details=dict(foo=3)) as (connection):
            self.driver.max_ports_per_switch = self.max_spanning
            port = self.driver.create_port(self.context, self.net_id,
                                           self.port_id)
            self.assertTrue("uuid" in port)
            self.assertTrue(connection.lswitch().create.called)
            self.assertTrue(connection.lswitch_port().create.called)
            self.assertTrue(connection.lswitch().query.called)
            status_args, kwargs = connection.lswitch_port().\
                admin_status_enabled.call_args
            self.assertTrue(True in status_args)

    def test_create_port_switch_not_exists_spanning(self):
        with self._stubs(has_lswitch=False, maxed_ports=True,
                         net_details=dict(foo=3)) as (connection):
            self.driver.max_ports_per_switch = self.max_spanning
            port = self.driver.create_port(self.context, self.net_id,
                                           self.port_id)
            self.assertTrue("uuid" in port)
            self.assertTrue(connection.lswitch().create.called)
            self.assertTrue(connection.lswitch_port().create.called)
            self.assertTrue(connection.lswitch().query.called)
            status_args, kwargs = connection.lswitch_port().\
                admin_status_enabled.call_args
            self.assertTrue(True in status_args)

    def test_create_disabled_port_switch_not_exists_spanning(self):
        with self._stubs(has_lswitch=False, maxed_ports=True,
                         net_details=dict(foo=3)) as (connection):
            self.driver.max_ports_per_switch = self.max_spanning
            port = self.driver.create_port(self.context, self.net_id,
                                           self.port_id, False)
            self.assertTrue("uuid" in port)
            self.assertTrue(connection.lswitch().create.called)
            self.assertTrue(connection.lswitch_port().create.called)
            self.assertTrue(connection.lswitch().query.called)
            status_args, kwargs = connection.lswitch_port().\
                admin_status_enabled.call_args
            self.assertTrue(False in status_args)


class TestNVPDriverLswitchesForNetwork(TestNVPDriver):
    @contextlib.contextmanager
    def _stubs(self, single_switch=True):
        with contextlib.nested(
            mock.patch("%s.get_connection" % self.d_pkg),
        ) as (get_connection,):
            connection = self._create_connection(switch_count=1)
            get_connection.return_value = connection
            yield connection

    def test_get_lswitches(self):
        """Test exists for coverage. No decisions are made."""
        with self._stubs() as connection:
            query_mock = mock.Mock()
            query_mock.tags = mock.Mock()
            query_mock.tagscopes = mock.Mock()
            connection.query = mock.Mock(return_value=query_mock)
            self.driver._lswitches_for_network(self.context, "net_uuid")


class TestSwitchCopying(TestNVPDriver):
    def test_no_existing_switches(self):
        switches = dict(results=[])
        args = self.driver._get_network_details(None, 1, switches)
        self.assertTrue(args == {})

    def test_has_switches_no_transport_zones(self):
        switch = dict(display_name="public", transport_zones=[])
        switches = dict(results=[switch])
        args = self.driver._get_network_details(None, 1, switches)
        self.assertEqual(args["network_name"], "public")
        self.assertEqual(args["phys_net"], None)

    def test_has_switches_and_transport_zones(self):
        transport_zones = [dict(zone_uuid="zone_uuid",
                                transport_type="bridge")]
        switch = dict(display_name="public", transport_zones=transport_zones)
        switches = dict(results=[switch])
        args = self.driver._get_network_details(None, 1, switches)
        self.assertEqual(args["network_name"], "public")
        self.assertEqual(args["phys_net"], "zone_uuid")
        self.assertEqual(args["phys_type"], "bridge")

    def test_has_switches_tz_and_vlan(self):
        binding = dict(vlan_translation=[dict(transport=10)])
        transport_zones = [dict(zone_uuid="zone_uuid",
                                transport_type="bridge",
                                binding_config=binding)]
        switch = dict(display_name="public", transport_zones=transport_zones)
        switches = dict(results=[switch])
        args = self.driver._get_network_details(None, 1, switches)
        self.assertEqual(args["network_name"], "public")
        self.assertEqual(args["phys_net"], "zone_uuid")
        self.assertEqual(args["phys_type"], "bridge")


class TestNVPDriverDeletePort(TestNVPDriver):
    @contextlib.contextmanager
    def _stubs(self, single_switch=True):
        with contextlib.nested(
            mock.patch("%s.get_connection" % self.d_pkg),
        ) as (get_connection,):
            if not single_switch:
                connection = self._create_connection(switch_count=2)
            else:
                connection = self._create_connection(switch_count=1)
            get_connection.return_value = connection
            yield connection

    def test_delete_port(self):
        with self._stubs() as (connection):
            self.driver.delete_port(self.context, self.port_id)
            self.assertTrue(connection.lswitch_port().delete.called)

    def test_delete_port_switch_given(self):
        with self._stubs() as (connection):
            self.driver.delete_port(self.context, self.port_id,
                                    self.lswitch_uuid)
            self.assertFalse(connection.lswitch_port().query.called)
            self.assertTrue(connection.lswitch_port().delete.called)

    def test_delete_port_many_switches(self):
        with self._stubs(single_switch=False):
            with self.assertRaises(Exception):
                self.driver.delete_port(self.context, self.port_id)
