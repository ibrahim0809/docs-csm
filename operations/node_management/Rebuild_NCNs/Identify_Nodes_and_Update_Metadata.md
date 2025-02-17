# Identify Nodes and Update Metadata

## Inspect and modify the JSON file

This section applies to all node types. The commands in this section assume you have set the variables from [the prerequisites section](../Rebuild_NCNs.md#Prerequisites).

### Step 1 - Generate the Boot Script Service \(BSS\) boot parameters JSON file

1. Run the following commands from a node that has cray cli initialized:

    ```bash
    cray bss bootparameters list --name $XNAME --format=json | jq .[] > ${XNAME}.json
    ```

### Step 2 - Modify the JSON file

1. Set the kernel parameters to wipe the disk.

    * Locate the portion of the line that contains `"metal.no-wipe"` and ensure it is set to zero `"metal.no-wipe=0"`.

### Step 3 - Re-apply the boot parameters list for the node using the JSON file

1. Get a token to interact with BSS using the REST API.

    ```bash
    ncn# TOKEN=$(curl -s -S -d grant_type=client_credentials \
        -d client_id=admin-client -d client_secret=`kubectl get secrets admin-client-auth \
        -o jsonpath='{.data.client-secret}' | base64 -d` \
        https://api-gw-service-nmn.local/keycloak/realms/shasta/protocol/openid-connect/token \
        | jq -r '.access_token')
    ```

1. Do a PUT action for the new JSON file.

    ```bash
    ncn# curl -i -s -H "Content-Type: application/json" -H "Authorization: Bearer ${TOKEN}" \
    "https://api-gw-service-nmn.local/apis/bss/boot/v1/bootparameters" -X PUT -d @./${XNAME}.json
    ```

    **IMPORTANT:** Ensure a good response \(`HTTP CODE 200`\) is returned in the output.

### Step 4 -  Verify the `bss bootparameters list` command returns the expected information.

1. Export the list from BSS to a file with a different name.

    ```bash
    ncn# cray bss bootparameters list --name ${XNAME} --format=json |jq .[]> ${XNAME}.check.json
    ```

1. Compare the new JSON file with what was PUT to BSS.

    ```bash
    ncn# diff ${XNAME}.json ${XNAME}.check.json
    ```

    * The files should be identical

[Click here for the Next Step](Wipe_Drives.md)

Or [Click here to returrn to the Main Page](../Rebuild_NCNs.md)