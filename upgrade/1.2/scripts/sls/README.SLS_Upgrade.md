# TL;DR
* Get a token: 
```
export TOKEN=$(curl -s -k -S -d grant_type=client_credentials -d client_id=admin-client -d client_secret=`kubectl get secrets admin-client-auth -o jsonpath='{.data.client-secret}' | base64 -d` https://api-gw-service-nmn.local/keycloak/realms/shasta/protocol/openid-connect/token | jq -r '.access_token')
```
* Dump SLS to a file:
```
curl -k -H "Authorization: Bearer ${TOKEN}" https://api_gw_service.local/apis/sls/v1/dumpstate | jq -S . > sls_input_file.json
```
* Example to show all options:
```
./sls_updater_csm_1.2.py --help
```
* Example to upgrade and toggle to the CHN (will by default output to `migrated_sls_file.json`)
```
./sls_updater_csm_1.2.py --sls-input-file sls_input_file.json --bican-user-network-name CHN --customer-highspeed-network 5 10.103.11.192/26
```
* Recommend reviewing migrated/upgraded data (using vimdiff or otherwise) for production systems and for systems which have many add-on components (UAN, login nodes, storage integration points, etc...).  Particlarly, review of subnet reservations to prevent any data loss is recommended.
* Upload migrated SLS file to SLS service:
```
curl -H "Authorization: Bearer ${TOKEN}" -k -L -X POST 'https://api_gw_service.local/apis/sls/v1/loadstate' -F 'sls_dump=@migrated_sls_file.json'
```

# Actions and Order
This migration script is performed offline for data security.  The running SLS file is first dumped, then the migration script is run and a new, migrated output file is created.

For large production systems:

    1. Migrate switch naming (in order):  leaf to leaf-bmc and agg to leaf.\n
    2. Remove api-gateway entries from HMLB subnets for CSM 1.2 security.\n
    3. Remove kubeapi-vip reservations for all networks except NMN.\n
    4. Create the new BICAN "toggle" network.\n
    5. Migrate the existing CAN to CMN.\n
    7. Create the CHN network.\n
    7. Convert IPs of the CAN network.\n
    8. Create MetalLB Pools and ASN entries on CMN and NMN networks.\n
    9. Update uai_macvlan in NMN dhcp ranges and uai_macvlan VLAN.\n
   10. Remove unused user networks (CAN or CHN) if requested [--remove-unused-user-network].

# Migrate switch names
Switch names change in CSM 1.2 and must be applied in the following order:
1. leaf switches become leaf-bmc switches
2. agg switches become leaf switches

This needs to be done in the order listed above. 

# Remove api-gw / istio-ingress-gateway reservations from HMNLB subnets
For CSM 1.2 the api gateway will no longer listen on the HMNLB metallb address pool.
These aliases provided DNS records and are being removed.

# Create the BICAN network "toggle"
New for CSM 1.2 the BICAN network ExtraProperties value of SystemDefaultRoute is used to point to the CAN, CHN or CMN and used by utilities to systemically toggle routes.

# Remove kubeapi-vip reservations for all networks except NMN
Self explanatory.  This endpoint now exists only on the NMN.

# Migrate (existing) CAN to (new) CMN
Using the existing CAN as a template, create the CMN.  The same IPs will be preserved for
NCNs (bootstrap_dhcp).  A new network_hardware subnet will be created where the end of the previous bootstrap_dhcp subnet existed to contain switching hardware.  MetalLB pools in the bootstrap_dhcp subnet will be shifted around to remain at the end of the new bootstrap subnet.

# Create the CHN network
With the original CAN as a template, the new CHN network will be created.  IP addresses will come from the `--customer-highspeed-network <vlan> <ipaddress>` (or its defaults). This will be created all the time and can be removed (if not needed/desired) by using the `--remove-unused-user-network` flag.

# Convert the IPs of the CAN network
Since the original/existing CAN has been converted to the new CMN, the CAN must have new IP addresses.  These are provided via the `--customer-access-network <vlan> <ipaddress>` (or its defaults).  This CAN conversion will happen all the time, but the new CAN may be removed (if not needed/desired) by using the `--remove-unused-user-network` flag.

# Add BGP peering info to CMN and NMN
MetalLB and switches now obtain BGP peers via SLS data.
```
  --bgp-asn INTEGER RANGE         The autonomous system number for BGP router
                                  [default: 65533;64512<=x<=65534]
  --bgp-cmn-asn INTEGER RANGE     The autonomous system number for CMN BGP
                                  clients  [default: 65534;64512<=x<=65534]
  --bgp-nmn-asn INTEGER RANGE     The autonomous system number for NMN BGP
                                  clients  [default: 65533;64512<=x<=65534]
```
In CMN and NMN:
```
  "Type": "ethernet",
  "ExtraProperties": {
    "CIDR": "10.102.3.0/25",
    "MTU": 9000,
    "MyASN": 65536,
    "PeerASN": 65533,
    "Subnets": [
      {
```

# Update uai_macvlan in NMN ranges and uai_macvlan VLAN
Self explanatory.  Ranges are used for the addresses of UAIs.

# Remove unused user networks (either CAN or CHN) if desired
Using the `--remove-unused-user-network` flag will remove the CAN if `--bican-user-network-name CHN` or will remove the CHN if `--bican-user-network-name CAN`.  
* Generally production systems will want to use this flag.
* Test/development systems may want to have all networks.
