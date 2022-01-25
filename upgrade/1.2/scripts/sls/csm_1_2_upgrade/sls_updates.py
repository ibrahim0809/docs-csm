# MIT License
#
# (C) Copyright [2022] Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
"""Functions used to update SLS from CSM 1.0.x to CSM 1.2."""
import ipaddress
import sys

import click
from sls_utils.ipam import (
    free_ipv4_addresses,
    free_ipv4_subnets,
    next_free_ipv4_address,
)
from sls_utils.Managers import SubnetManager
from sls_utils.Networks import BicanNetwork
from sls_utils.Networks import Network
from sls_utils.Networks import Subnet
from sls_utils.Reservations import Reservation


def migrate_switch_names(networks):
    """Rename CSM <=1.0.x switches to new CSM 1.2 naming.

    CSM 1.2 changes switch names in the following order:
      1. sw-leaf-xyz -> sw-leaf-bmc-xyz
      2. sw-agg-xyz -> sw-leaf-xyz

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
    """
    # Use existence of agg switches in network_hardware subnet in the
    # MTL network to determine if switch naming needs to be done.
    #
    # WARNING:  If this check is not in place the script is not guaranteed to
    # be idempotent!
    subnet = "network_hardware"
    mtl_network_hardware_subnet = networks.get("MTL").subnets().get(subnet)
    aggregation_switches = [
        reservation
        for reservation in mtl_network_hardware_subnet.reservations().keys()
        if "agg" in reservation
    ]
    if not aggregation_switches:
        return

    click.secho("Migrating switch naming.", fg="bright_white")
    for network in networks.values():
        if network.subnets().get(subnet) is None:
            continue
        reservations = network.subnets().get(subnet).reservations()

        click.echo(
            "    Renaming sw-leaf to sw-leaf-bmc in reservations "
            f"for subnet {subnet} in network {network.name()}.",
        )
        for reservation in reservations.values():
            if not reservation.name().find("leaf"):
                continue
            reservation.name(reservation.name().replace("leaf", "leaf-bmc"))

        click.echo(
            "    Renaming sw-agg  to sw-leaf     in reservations "
            f"for subnet {subnet} in network {network.name()}.",
        )
        for reservation in reservations.values():
            if not reservation.name().find("agg"):
                continue
            reservation.name(reservation.name().replace("agg", "leaf"))

        # Change reservation key names (internal to library)
        for old_key in list(reservations):
            new_key = old_key.replace("leaf", "leaf-bmc")
            reservations[new_key] = reservations.pop(old_key)
        for old_key in list(reservations):
            new_key = old_key.replace("agg", "leaf")
            reservations[new_key] = reservations.pop(old_key)


def remove_api_gw_from_hmnlb_reservations(networks):
    """Remove istio ingress (api-gw) from the existing HMNLB network.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
    """
    network = "HMNLB"
    subnet = "hmn_metallb_address_pool"
    reservations = networks.get(network).subnets().get(subnet).reservations()
    for delete_reservation in ["istio-ingressgateway", "istio-ingressgateway-local"]:
        if reservations.pop(delete_reservation, None) is not None:
            click.secho(
                f"Removing api-gw aliases {delete_reservation} from {network} {subnet}",
                fg="bright_white",
            )


def remove_kube_api_reservations(networks):
    """Remove kube-api from all networks except NMN.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
    """
    click.secho(
        "Removing kubeapi-vip reservations from all network except NMN",
        fg="bright_white",
    )
    for network in networks.values():
        if network.name() == "NMN":
            continue
        for subnet in network.subnets().values():
            if subnet.reservations().get("kubeapi-vip") is not None:
                subnet.reservations().pop("kubeapi-vip")


def update_nmn_uai_macvlan_dhcp_ranges(networks):
    """Update the DHCP Start and End ranges for NMN mac_vlan subnet.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
    """
    nmn_network = networks.get("NMN")
    uai_macvlan_subnet = nmn_network.subnets().get("uai_macvlan")
    if uai_macvlan_subnet is None:
        return

    click.secho(
        "Updating DHCP Start and End Ranges for uai_macvlan subnet in NMN network",
        fg="bright_white",
    )
    reservations = [
        x.ipv4_address() for x in uai_macvlan_subnet.reservations().values()
    ]
    dhcp_start = max(reservations) + 1
    dhcp_end = sorted(free_ipv4_addresses(uai_macvlan_subnet))[-1]
    uai_macvlan_subnet.dhcp_start_address(dhcp_start)
    uai_macvlan_subnet.dhcp_end_address(dhcp_end)

    click.secho(
        "Updating uai_macvlan subnet VLAN in NMN network",
        fg="bright_white",
    )
    nmn_vlan = nmn_network.subnets().get("bootstrap_dhcp").vlan()
    uai_macvlan_subnet.vlan(nmn_vlan)


def create_bican_network(networks, default_route_network_name):
    """Create a new SLS BICAN network data structure.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
        default_route_network_name (str): Name of the user network for bifurcated CAN
    """
    if networks.get("BICAN") is None:
        click.secho(
            f"Creating new BICAN network and toggling to {default_route_network_name}.",
            fg="bright_white",
        )
        bican = BicanNetwork(default_route_network_name=default_route_network_name)
        networks.update({bican.name(): bican})


def create_metallb_pools_and_asns(networks, bgp_asn, bgp_nmn_asn, bgp_cmn_asn):
    """Update the NMN and CMN by creating the BGP peering.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
        bgp_asn (int): Remote peer BGP ASN
        bgp_nmn_asn (int): Local NMN BGP ASN
        bgp_cmn_asn (int): Local CMN BGP ASN
    """
    click.secho(
        "Creating BGP peering ASNs and MetalLBPool names",
        fg="bright_white",
    )
    nmn = networks.get("NMN")
    if nmn is not None and None in nmn.bgp():
        click.echo(
            f"    Updating the NMN network with BGP peering info MyASN: {bgp_nmn_asn} and PeerASN: {bgp_asn}",
        )
        nmn.bgp(bgp_nmn_asn, bgp_asn)  # bgp(my_asn, peer_asn)

    cmn = networks.get("CMN")
    if cmn is not None and None in cmn.bgp():
        click.echo(
            f"    Updating the CMN network with BGP peering info MyASN: {bgp_cmn_asn} and PeerASN: {bgp_asn}",
        )
        cmn.bgp(bgp_cmn_asn, bgp_asn)

    metallb_subnet_name_map = {
        "can_metallb_address_pool": "customer-access",
        "chn_metallb_address_pool": "customer-high-speed",
        "cmn_metallb_static_pool": "customer-management-static",
        "cmn_metallb_address_pool": "customer-management",
        "hmn_metallb_address_pool": "hardware-management",
        "nmn_metallb_address_pool": "node-management",
    }

    for network in networks.values():
        for subnet in network.subnets().values():
            pool_name = metallb_subnet_name_map.get(subnet.name())
            if pool_name is None:
                continue
            click.echo(
                f"    Updating {subnet.name()} subnet in the {network.name()} network with MetalLBPoolName {pool_name}",
            )
            subnet.metallb_pool_name(pool_name)


def create_chn_network(networks, chn_data):
    """Create a new SLS CHN data structure.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
        chn_data (int, ipaddress.IPv4Network): VLAN and IPv4 CIDR for the CHN
    """
    if networks.get("CHN") is not None:
        return

    chn_vlan = chn_data[0]
    chn_ipv4 = chn_data[1]
    click.secho(
        f"Creating CHN network with VLAN: {chn_vlan} and IPv4 CIDR: {chn_ipv4}",
        fg="bright_white",
    )
    chn = Network("CHN", "ethernet", chn_ipv4)
    chn.full_name("Customer High-Speed Network")
    chn.mtu(9000)

    # Clone CAN subnets for structure
    for can_subnet in networks.get("CAN").subnets().values():
        chn.subnets().update(
            {can_subnet.name(): Subnet.subnet_from_sls_data(can_subnet.to_sls())},
        )

    # Clean up subnet naming
    for subnet in chn.subnets().values():
        subnet.name(subnet.name().replace("can_", "chn_"))
        subnet.full_name(subnet.full_name().replace("CAN", "CHN"))
        click.echo(f"    Updating subnet naming for {subnet.name()}")

        click.echo(f"    Updating reservation names and aliases for {subnet.name()}")
        for reservation in subnet.reservations().values():
            reservation.name(reservation.name().replace("can-", "chn-"))
            reservation.name(reservation.name().replace("-can", "-chn"))

            if reservation.aliases() is None:
                continue

            for i, alias in enumerate(reservation.aliases()):
                reservation.aliases()[i] = alias.replace("-can", "-chn")

    bootstrap = chn.subnets().get("bootstrap_dhcp")
    click.echo(
        f"    Updating subnet IPv4 addresses for {bootstrap.name()} to {chn_ipv4}",
    )
    bootstrap.ipv4_address(chn_ipv4)
    bootstrap.ipv4_gateway(list(chn_ipv4.hosts())[0])
    bootstrap.vlan(chn_vlan)

    pool_subnets = list(bootstrap.ipv4_network().subnets())[
        1
    ]  # Last half of bootstrap.
    pool_subnets = list(pool_subnets.subnets())  # Split it in two.

    click.echo(f"    Updating reservation IPv4 addresses for {bootstrap.name()}")
    for reservation in bootstrap.reservations().values():
        reservation.ipv4_address(next_free_ipv4_address(bootstrap))

    hold_ipv4 = bootstrap.ipv4_network()
    bootstrap.ipv4_address(f"{hold_ipv4.network_address}/{hold_ipv4.prefixlen+1}")

    dhcp_start = next_free_ipv4_address(bootstrap)
    dhcp_end = sorted(free_ipv4_addresses(bootstrap))[-1]
    click.echo(f"    Updating DHCP start-end IPv4 addresses {dhcp_start}-{dhcp_end}")
    bootstrap.dhcp_start_address(dhcp_start)
    bootstrap.dhcp_end_address(dhcp_end)

    bootstrap.ipv4_address(hold_ipv4)

    # Update MetalLB pool subnets
    for subnet in chn.subnets().values():
        if subnet.name() == "bootstrap_dhcp":
            continue
        subnet_ipv4_address = pool_subnets.pop(0)
        subnet_ipv4_gateway = list(subnet_ipv4_address.hosts())[0]
        subnet.ipv4_address(subnet_ipv4_address)
        subnet.ipv4_gateway(subnet_ipv4_gateway)
        subnet.vlan(chn_vlan)

        if subnet.reservations() is None:
            continue

        for reservation in subnet.reservations().values():
            reservation.ipv4_address(next_free_ipv4_address(subnet))

    networks.update({"CHN": chn})


def convert_can_ips(networks, can_data):
    """Update existing CAN IPv4 addresses.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
        can_data (int, ipaddress.IPv4Network): VLAN and IPv4 CIDR for the CAN
    """
    can_network = networks.get("CAN")
    if can_network is None:
        return

    click.secho("Updating existing CAN IPv4 addresses", fg="bright_white")

    can_ipv4_network = can_data[1]
    can_vlan = can_data[0]
    can_network.ipv4_address(can_ipv4_network)

    click.echo(
        f"    Updating existing bootstrap_dhcp addresses with {can_ipv4_network}",
    )
    bootstrap_subnet = can_network.subnets().get("bootstrap_dhcp")
    bootstrap_ipv4_address = list(can_ipv4_network.subnets())[
        0
    ]  # First half of CAN network
    bootstrap_subnet.ipv4_address(bootstrap_ipv4_address)
    bootstrap_subnet.ipv4_gateway("0.0.0.0")  # Blank slate to prevent overlaps
    bootstrap_subnet.ipv4_gateway(sorted(free_ipv4_addresses(bootstrap_subnet))[0])
    bootstrap_subnet.vlan(can_vlan)

    click.echo(
        f"    Updating existing bootstrap_dhcp reservations from {bootstrap_ipv4_address}",
    )
    # Blank slate all reservations to prevent overlaps
    for reservation in bootstrap_subnet.reservations().values():
        reservation.ipv4_address("0.0.0.0")
    for reservation in bootstrap_subnet.reservations().values():
        reservation.ipv4_address(next_free_ipv4_address(bootstrap_subnet))

    dhcp_start = next_free_ipv4_address(bootstrap_subnet)
    dhcp_end = sorted(free_ipv4_addresses(bootstrap_subnet))[-1]
    click.echo(
        f"    Updating existing bootstrap_dhcp DHCP start-end from {dhcp_start}-{dhcp_end}",
    )
    bootstrap_subnet.dhcp_start_address(dhcp_start)
    bootstrap_subnet.dhcp_end_address(dhcp_end)

    pool_subnets = list(can_ipv4_network.subnets())[1]  # Second half of CAN network
    pool_subnets = list(pool_subnets.subnets())  # Split in two
    for subnet in can_network.subnets().values():
        if subnet.name() == "bootstrap_dhcp":
            continue

        ipv4_address = pool_subnets.pop(0)
        click.echo(f"    Updating existing {subnet.name()} subnet from {ipv4_address}")
        subnet.ipv4_address(ipv4_address)
        subnet.ipv4_gateway(sorted(ipv4_address.hosts())[0])
        subnet.vlan(can_vlan)
        click.echo(f"    Updating existing {subnet.name()} reservations")
        # Blank slate existing reservations to prevent overlaps
        for reservation in subnet.reservations().values():
            reservation.ipv4_address("0.0.0.0")
        for reservation in subnet.reservations().values():
            reservation.ipv4_address(next_free_ipv4_address(subnet))

    # Apply supernet hack
    bootstrap_subnet.ipv4_address(can_ipv4_network)


def migrate_can_to_cmn(networks):
    """Convert an existing CAN network in sls to the new CMN.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
    """
    can_network = networks.get("CAN")
    if can_network is None:
        return

    if networks.get("CMN") is not None:
        return

    click.secho("Converting existing CAN network to CMN.", fg="bright_white")

    # Build up the base CMN network
    can_ipv4_network = can_network.ipv4_network()
    cmn_vlan = can_network.subnets().get("bootstrap_dhcp").vlan()
    cmn_network = Network("CMN", "ethernet", can_ipv4_network)
    cmn_network.full_name("Customer Management Network")
    cmn_network.mtu(can_network.mtu())

    # CAN subnets are an atypical mess.  The bootstrap_dhcp subnet takes up the entire CAN
    # network range, while the metallb pool "subnets" are actually inside the bootstrap_dhcp
    # subnet.
    #
    # To convert a CAN to a CMN we need to attempt too preserve the existing Reservations
    # while adding the system switches via a (new) network_hardware subnet.  This will
    # require recalculation of the bootstrap_dhcp and possibly it's containing network.

    #
    # Create the new bootstrap_dhcp network in the CMN
    #
    bootstrap_dhcp_ipv4_network = (
        f"{can_ipv4_network.network_address}/{can_ipv4_network.prefixlen+1}"
    )
    click.echo(
        f"    Creating the bootstrap_dhcp network with {bootstrap_dhcp_ipv4_network}",
    )
    old_subnet = can_network.subnets().get("bootstrap_dhcp")
    new_subnet = Subnet(
        old_subnet.name(),
        bootstrap_dhcp_ipv4_network,
        old_subnet.ipv4_gateway(),
        cmn_vlan,
    )
    new_subnet.full_name("CMN Bootstrap DHCP Subnet")

    # Create a copy of the CAN reservations for bootstrap_dhcp keeping IPv4 addresses
    old_reservations = old_subnet.reservations().values()
    for old in old_reservations:
        # Create the new reservation
        new = Reservation(
            old.name(),
            old.ipv4_address(),
            [a.replace("-can", "-cmn") for a in old.aliases()],
            old.comment(),
        )
        new_subnet.reservations().update({new.name(): new})
    cmn_network.subnets().update({new_subnet.name(): new_subnet})

    # Collect the DHCP Start address. Must do it here because removing the
    # can-switches will create a gap that rudimentary IPAM can't deal with.
    bootstrap_dhcp_start = next_free_ipv4_address(new_subnet)
    click.echo(f"    Updating DHCP Start address to {bootstrap_dhcp_start}")
    new_subnet.dhcp_start_address(bootstrap_dhcp_start)

    # Collect the DHCP End address.  Must game the system here since
    # below we use the 2nd half of the bootstrap_subnet to contain
    # MetalLB pools.  Reserve last address as in CSI.
    address = new_subnet.ipv4_network().network_address
    prefix = new_subnet.ipv4_network().prefixlen
    bootstrap_dhcp_end = list(ipaddress.IPv4Network(f"{address}/{prefix+1}").hosts())[
        -1
    ]
    click.echo(f"    Updating DHCP End address to {bootstrap_dhcp_end}")
    new_subnet.dhcp_end_address(bootstrap_dhcp_end)

    # Remove switches from bootstrap.  Adding them to network_hardware
    for switch in ["can-switch-1", "can-switch-2"]:
        if new_subnet.reservations().get(switch) is not None:
            new_subnet.reservations().pop(switch)

    #
    # Create the new network_hardware network in the CMN
    #
    network_hardware_ipv4_network = free_ipv4_subnets(cmn_network)
    if network_hardware_ipv4_network is None:
        click.secho(
            f"ERROR:  Cannot allocate a subnet in {cmn_network.name()} for network_hardware",
            fg="red",
        )
        click.echo(f"    Network: {cmn_network.name()} {cmn_network.ipv4_network()}")
        for subnet in cmn_network.subnets().values():
            click.echo(f"    Existing Subnets: {subnet.name()} {subnet.ipv4_address()}")
        sys.exit(1)
    network_hardware_ipv4_network = network_hardware_ipv4_network[0]

    click.echo(
        f"    Creating the network_hardware network with {network_hardware_ipv4_network}",
    )
    old_subnet = networks.get("MTL").subnets().get("network_hardware")
    new_subnet = Subnet(
        old_subnet.name(),
        network_hardware_ipv4_network,
        "0.0.0.0",
        cmn_vlan,
    )
    new_subnet.full_name("CMN Network Hardware Subnet")
    new_subnet.ipv4_gateway(next_free_ipv4_address(new_subnet))

    # Create a copy of the CAN reservations for bootstrap_dhcp keeping IPv4 addresses
    old_reservations = old_subnet.reservations().values()
    for old in old_reservations:
        # Create the new reservation
        new = Reservation(
            old.name(),
            next_free_ipv4_address(new_subnet),
            [a.replace("-can", "-cmn") for a in old.aliases()],
            old.comment(),
        )
        new_subnet.reservations().update({new.name(): new})
    cmn_network.subnets().update({new_subnet.name(): new_subnet})

    #
    # Add MetalLB pools to bootstrap_dhcp
    #
    # Here we play a game by adding temporary subnets to the bootstrap_dhcp network
    # to calculate the new pool subnets (which need to be overlapping but shouldn't).
    bootstrap_subnet = cmn_network.subnets().get("bootstrap_dhcp")
    pool_subnets = list(bootstrap_subnet.ipv4_network().subnets())[
        1
    ]  # Last half of bootstrap
    pool_subnets = list(pool_subnets.subnets())  # Split in two

    static_pool_ipv4_network = pool_subnets[0]
    dynamic_pool_ipv4_network = pool_subnets[1]

    # Create the MetalLB static pool
    click.echo(
        f"    Creating MetalLB static pool {static_pool_ipv4_network} in the bootstrap_dhcp subnet",
    )
    old_static_pool = can_network.subnets().get("can_metallb_static_pool").to_sls()
    cmn_metallb_static_pool = Subnet.subnet_from_sls_data(old_static_pool)
    cmn_metallb_static_pool.full_name("CMN Static Pool MetalLB")
    cmn_metallb_static_pool.ipv4_address(static_pool_ipv4_network)
    cmn_metallb_static_pool.ipv4_gateway(list(static_pool_ipv4_network.hosts())[0])
    for reservation in cmn_metallb_static_pool.reservations().values():
        reservation.ipv4_address(next_free_ipv4_address(cmn_metallb_static_pool))
    cmn_network.subnets().update(
        {cmn_metallb_static_pool.name(): cmn_metallb_static_pool},
    )

    # Create MetalLB dynamic pool
    click.echo(
        f"    Creating MetalLB dyanmic pool {dynamic_pool_ipv4_network} in the bootstrap_dhcp subnet",
    )
    old_dynamic_pool = can_network.subnets().get("can_metallb_address_pool").to_sls()
    cmn_metallb_address_pool = Subnet.subnet_from_sls_data(old_dynamic_pool)
    cmn_metallb_address_pool.full_name("CMN Dynamic MetalLB")
    cmn_metallb_address_pool.ipv4_address(dynamic_pool_ipv4_network)
    cmn_metallb_address_pool.ipv4_gateway(list(dynamic_pool_ipv4_network.hosts())[0])
    for reservation in cmn_metallb_address_pool.reservations().values():
        reservation.ipv4_address(next_free_ipv4_address(cmn_metallb_address_pool))
    cmn_network.subnets().update(
        {cmn_metallb_address_pool.name(): cmn_metallb_address_pool},
    )

    #
    # Apply the supernet hack
    #
    hacked_subnets = ["bootstrap_dhcp", "network_hardware"]
    hacked_address = cmn_network.ipv4_network()
    hacked_gateway = list(hacked_address.hosts())[0]
    for subnet in cmn_network.subnets().values():
        if subnet.name() in hacked_subnets:
            click.echo(
                f"    Applying supernet hack {hacked_address}/{hacked_gateway} to {subnet.name()}",
            )
            subnet.ipv4_address(hacked_address)
            subnet.ipv4_gateway(hacked_gateway)

    networks.update({"CMN": cmn_network})


def convert_can_to_cmn_hold(networks):
    """Convert an existing CAN network in sls to the new CMN.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
    """
    if networks.get("CAN") is None:
        return

    if networks.get("CMN") is not None:
        click.secho("Existing CMN network skips CAN conversion.", fg="bright_white")
        return

    click.secho("Converting existing CAN network to CMN.", fg="bright_white")

    click.echo("    Renaming CAN to CMN in Network properties.")
    cmn = networks.get("CAN")
    networks["CMN"] = networks.pop("CAN")
    cmn.name("CMN")
    cmn.full_name("Customer Management Network")

    cmn_subnets = SubnetManager(cmn.subnets())

    click.echo("    Renaming all can_ names to cmn_ naming in Subnets")
    click.echo("    Renaming all -can aliases to -cmn aliases in Reservations")
    # Retrofit subnet values of CAN/can to CMN/cmn
    for subnet in cmn_subnets.values():
        subnet.name(subnet.name().replace("can_", "cmn_"))
        subnet.full_name(subnet.full_name().replace("CAN", "CMN"))

        # Retrofit aliases from can to cmn
        reservations = subnet.reservations()
        for reservation in reservations.values():
            if reservation.aliases() is None:
                continue
            for i, alias in enumerate(reservation.aliases()):
                reservation.aliases()[i] = alias.replace("-can", "-cmn")

    # Change subnet key names - can to cmn (internal to library)
    for old_key in list(cmn_subnets):
        new_key = old_key.replace("can_", "cmn_")
        cmn_subnets[new_key] = cmn_subnets.pop(old_key)

    # TODO:
    # * Insert network_hardware subnet
    # * Remove can-switch entries in bootstrap_dhcp


def sls_and_input_data_checks(networks, bican_name, can_data, chn_data):
    """Check input values and SLS data for proper logic.

    Args:
        networks (sls_utils.Managers.NetworkManager): Dictionary of SLS networks
        bican_name (str): Name of the user network for bifurcated CAN
        can_data (int, ipaddress.IPv4Network): VLAN and IPv4 CIDR for the CAN
        chn_data (int, ipaddress.IPv4Network): VLAN and IPv4 CIDR for the CHN
    """
    click.secho(
        "Checking input values and SLS data for proper logic.",
        fg="bright_white",
    )

    can = networks.get("CAN")
    if can is not None:
        click.secho(
            "    INFO: A CAN network already exists in SLS.",
            fg="white",
        )
        if can_data[1] == ipaddress.IPv4Network("10.103.6.0/24"):
            click.secho(
                "    WARNING: CAN network found, but command line --customer-access-network values not found. "
                "Using [default: 6, 10.103.6.0/24]",
                fg="bright_yellow",
            )

    cmn = networks.get("CMN")
    if cmn is not None:
        click.secho(
            "    INFO: A CMN network already exists in SLS.  This is unusual except where the "
            "upgrade process has already run or on an existing CSM 1.2 system.",
            fg="white",
        )

    chn = networks.get("CHN")
    if chn is not None:
        click.secho(
            "    INFO: A CHN network already exists in SLS.  This is unusual except where the "
            "upgrade process has already run or on an existing CSM 1.2 system.",
            fg="white",
        )
    if bican_name == "CHN":
        if chn_data[1] == ipaddress.IPv4Network("10.104.7.0/24"):
            click.secho(
                "    WARNING: Command line --customer-highspeed-network values not found. "
                "Using [default: 5, 10.104.7.0/24]",
                fg="bright_yellow",
            )
    nmn = networks.get("NMN")
    if nmn is not None:
        if None not in nmn.bgp():
            click.secho(
                "    WARNING: BGP Peering information exists in the NMN network and will be overwritten.",
                fg="bright_yellow",
            )
