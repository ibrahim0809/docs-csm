## Manage System Passwords

Many system services require login credentials to gain access to them. The information below is a comprehensive list of system passwords and how to change them.

Contact HPE Cray service in order to obtain the default usernames and passwords for any of these components or services.

For Linux user account password management on NCNs, see [Update NCN Passwords](Update_NCN_Passwords.md).

### Keycloak

Default Keycloak admin user login credentials:

-   Username: admin
-   The password can be obtained with the following command:

    ```bash
    ncn-w001# kubectl get secret -n services keycloak-master-admin-auth \
    --template={{.data.password}} | base64 --decode
    ```


To update the default password for the admin account, refer to [Change the Keycloak Admin Password](Change_the_Keycloak_Admin_Password.md).

To create new accounts, refer to [Create Internal User Accounts in the Keycloak Shasta Realm](Create_Internal_User_Accounts_in_the_Keycloak_Shasta_Realm.md).

### Gitea

The initial Gitea login credentials for the `crayvcs` username are stored in three places:

-   vcs-user-credentials Kubernetes secret - This is used to initialize the other two locations, as well as providing a place where users can query for the password.

    The password can be obtained using this command:

    ```bash
    ncn-w001# kubectl get secret -n services vcs-user-credentials \
    --template={{.data.vcs_password}} | base64 --decode
    ```

    The password can be changed using this command:

    ```bash
    ncn-w001# kubectl create secret generic vcs-user-credentials \
    --save-config --from-literal=vcs_username="crayvcs" --from-literal=vcs_password="NEW_PASSWORD" \
    --dry-run -o yaml | kubectl apply -f -
    ```

-   Gitea - These credentials are used when pushing to Git using the default username and password. The password should be changed through the Gitea UI.

-   Keycloak - These credentials are used to allow access to the Gitea UI. They must be changed through Keycloak.

**IMPORTANT:** These three sources of credentials are not currently synced by any mechanism, and so changing the default password requires that it be changed in all three places. Changing only one many result in difficulty determining the password at a later date, or may result in lost access to Gitea.

### System Management Health Service

Contact HPE Cray service in order to obtain the default password for Grafana and Kiali. The default username is admin.

### Management Network Switches

Each rack type includes a different set of passwords. During different stages of installation, these passwords are subject to change. Contact HPE Cray service in order to obtain the default passwords.

The tables below include the default login credentials for each rack type. These passwords can be changed by going into the console on a given switch and changing it. However, if the user gets locked out attempting to change the password or the configuration gets corrupted for an individual switch, it can wipe out the entire network configuration for the system.

**Liquid Cooled Cabinet:**

| Name  | Role      | Switch          | IP Address | Login |
| ----- | --------- | --------------- | ---------- | ----- |
| smn01 | Leaf/Mgmt | Dell S3048-ON   | 10.254.0.2 | admin |
| smn02 | Spine-001 | Mellanox SN2100 | 10.254.0.1 | admin |
| smn03 | Spine-002 | Mellanox SN2100 | 10.254.0.3 | admin |

**Air Cooled Cabinet:**

| Name    | Role      | Switch        | IP Address | Login |
| ------- | --------- | ------------- | ---------- | ----- |
| mtnsw01 | Leaf/Mgmt | Dell S3048-ON | 10.254.0.2 | admin |

**Coolant Distribution Unit (CDU):**

| Name   | Role | Switch         | IP Address | Login |
| ------ | ---- | -------------- | ---------- | ----- |
| cdu-s1 | CDU  | Dell S4048T-ON | 10.254.0.2 | admin |

**ClusterStor:**

| Name     | Role                  | Switch         | IP Address    | Login |
| -------- | --------------------- | -------------- | ------------- | ----- |
| Arista   |                       | DCS-7060CX-32S | 172.16.249.10 | admin |
| Sonexion | Entry point to Arista | CS-L300        | 172.30.49.178 | admin |


### Redfish Credentials

Redfish accounts are only valid with the Redfish API. They do not allow system logins via `ssh` or serial console. Three accounts are created by default:

-   Root - Administrative account
    -   Username: root
    -   Password: <your password>
-   Operator - Power components on/off, read values, and configure accounts
    -   Username: operator
    -   Password: <your password>
-   ReadOnly - Log in, configure self, and read values
    -   Username: guest
    -   Password: <your password>

Contact HPE Cray service in order to obtain the default passwords.

The account database is automatically saved to the non-volatile settings partition \(/nvram/redfish/redfish-accounts\) any time an account or account policy is modified. The file is stored as a redis command dump and is replayed \(if it exists\) anytime the core Redfish schema is loaded via the init script. If default accounts must be restored, delete the redis command dump and reboot the controller.

**List accounts:**

Use the following API path to list all accounts:

```bash
GET /redfish/v1/AccountService/Accounts

    {
        "@odata.context": "/redfish/v1/$metadata#ManagerAccountCollection.ManagerAccountCollection",
        "@odata.etag": "W/\"1559675674\"",
        "@odata.id": "/redfish/v1/AccountService/Accounts",
        "@odata.type": "#ManagerAccountCollection.ManagerAccountCollection",
        "Description": "Collection for Manager Accounts",
        "Members": [
        {
            "@odata.id": "/redfish/v1/AccountService/Accounts/1"
        },
        {
            "@odata.id": "/redfish/v1/AccountService/Accounts/2"
        }
        ],
        "Members@odata.count": 2,
        "Name": "Accounts Collection"
    }

```

Use the following API path to list a single account:

```bash
GET /redfish/v1/AccountService/Accounts/1

    {
        "@odata.context": "/redfish/v1/$metadata#ManagerAccount.ManagerAccount(*)",
        "@odata.etag": "W/"1559675272"",
        "@odata.id": "/redfish/v1/AccountService/Accounts/1",
        "@odata.type": "#ManagerAccount.v1_1_1.ManagerAccount",
        "Description": "Default Account",
        "Enabled": true,
        "Id": "1",
        "Links": {
            "Role": {
                "@odata.id": "/redfish/v1/AccountService/Roles/Administrator"
            }
        },
        "Locked": false,
        "Name": "Default Account",
        "RoleId": "Administrator",
        "UserName": "root"
    }
```

**Add accounts:**

If an account is successfully created, then the account information data structure will be returned. The most important bit returned is the Id because it is part of the URL used for any further manipulation of the account. Use the following API path to add accounts:

```bash
POST /redfish/v1/AccountService/Accounts

    Content-Type: application/json
    {
        "Name": "Test Account",
        "RoleId": "Administrator",
        "UserName": "test",
        "Password": "test123",
        "Locked": false,
        "Enabled": true
    }

    Response:
    {
        "@odata.context": "/redfish/v1/$metadataAccountService/Members/Accounts",
        "@odata.etag": "W/"1559679136"",
        "@odata.id": "/redfish/v1/AccountService/Accounts",
        "@odata.type": "#ManagerAccount.v1_1_1.ManagerAccount",
        "Description": "Collection of Account Details",
        "Id": "5",  **<<-- Note this value**
        "Links": {
            "Role": {
                "@odata.id": "/redfish/v1/AccountService/Roles/Administrator"
            }
        },
        "Enabled": true,
        "Locked": false,
        "Name": "Test",
        "RoleId": "Administrator",
        "UserName": "test"
    }
```

**Delete accounts:**

Delete an account with the curl command:

```bash
# curl -u root:xxx -X DELETE https://x0c0s0b0/redfish/v1/AccountService/Accounts/ACCOUNT_ID
```

**Update passwords:**

Update an account's password with the curl command:

> **WARNING**: Changing Redfish credentials outside of Cray System Management (CSM) services may cause the Redfish device to be no longer manageable under CSM.
> If the credentials for other devices need to be changed, refer to the following device-specific credential changing procedures:
> - To change liquid-cooled BMC credentials, refer to [Change Cray EX Liquid-Cooled Cabinet Global Default Password](../security_and_authentication/Change_EX_Liquid-Cooled_Cabinet_Global_Default_Password.md).
> - To change air-cooled Node BMC credentials, refer to [Change Air-Cooled Node BMC Credentials](../security_and_authentication/Change_Air-Cooled_Node_BMC_Credentials.md).
> - To change Slingshot switch BMC credentials, refer to "Change Rosetta Login and Redfish API Credentials" in the *Slingshot Operations Guide (> 1.6.0)*.

```bash
# curl -u root:xxx -X PATCH \
-H 'Content-Type: application/json' \
-d '{"Name": "Test"}' \
https://x0c0s0b0/redfish/v1/AccountService/Accounts/ACCOUNT_ID
```

### System Controllers

For SSH access, the system controllers have the following default credentials:

-   Node controller \(nC\)
    -   Username: root
    -   Password: <your password>
-   Chassis controller \(cC\)
    -   Username: root
    -   Password: <your password>
-   Switch controller \(sC\)
    -   Username: root
    -   Password: <your password>
-   sC minimal recovery firmware image \(rec\)
    -   Username: root
    -   Password: <your password>

Contact HPE Cray service in order to obtain the default passwords.

Passwords for nC, cC, and sC controllers are all managed with the following process. The cfgsh tool is a configuration shell that can be used interactively or scripted. Interactively, it may be used as follows after logging in as root via `ssh`:

```bash
x0c1# config
x0c1(conf)# CURRENT_PASSWORD root NEW_PASSWORD
x0c1(conf)# exit
x0c1# copy running-config startup-config
x0c1# exit
```

It may be used non-interactively as well. This is useful for separating out several of the commands used for the initial setup. The shell utility returns non-zero on error.

```bash
# cfgsh --config CURRENT_PASSWORD root NEW_PASSWORD
# cfgsh copy running-config startup-config
```

In both cases, a `running-config` must be saved out to non-volatile storage in a startup configuration file. If it is not, the password will revert to default on the next boot. This is the exact same behavior as standard managed Ethernet switches.

### Gigabyte

Contact HPE Cray service in order to obtain the default password for Gigabyte. The default username is admin.
