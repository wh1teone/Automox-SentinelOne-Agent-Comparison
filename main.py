import requests
import csv
from datetime import datetime
#############################
#--------CONSTANTS----------#
#############################

AUTOMOX_API_KEY = ""
AUTOMOX_API_URL = "https://console.automox.com/api/"
AUTOMOX_REQUEST_HEADERS = {"Authorization": "Bearer " + f"{AUTOMOX_API_KEY}"}
AUTOMOX_ACCOUNT_ID = ""
SENTINELONE_API_KEY = ""
SENTINELONE_API_URL = "https://<FILL URL HERE>/web/api/v2.1/"
SENTINELONE_REQUEST_HEADERS = {"Authorization": f"ApiToken {SENTINELONE_API_KEY}"}
automox_duplicate_devices_dict = {}
sentinelone_unadded_sites_dict = {}
automox_unadded_sites_dict = {}
SENTINELONE_ACCOUNT_IDS_DICT = {"<INSERT ACCOUNT NAME>": "INSERT ACCOUNT ID (INT)"}
sentinelone_nested_site_endpoint_dict = {} #needs to be global for second round of inspection by endpoint name
automox_nested_site_endpoint_dict = {} #needs to be global for second round of inspection by endpoint name
both_platform_sentinelone_site_dicts = {}
to_print_at_startup ="""

This script compares endpoints amounts in Automox, SentinelOne and both platforms.
It performs check based on two rounds:
1. it verifies the endpoint identity based on mac address
2. after that, it verifies the endpoint identity based on endpoint name.
Script running...       
"""

##############################

def sentinelone_get_response(s1_endpoint_url, s1_req_parameter=dict()):
    """
    returns a response from sentinelone's  api according to URL and params passed to the function.
    :param s1_endpoint_url: endpoint to be requested
    :param s1_req_parameter: params to be passed with the request
    :return: s1 response
    """
    s1_it_res = requests.get(f"{SENTINELONE_API_URL}{s1_endpoint_url}",
                                   headers=SENTINELONE_REQUEST_HEADERS, params=s1_req_parameter).json()
    if not s1_it_res:
        print(f"[-] There was an issue getting a response from SentinelOne."
              f"\n Try checking your API key or console downtime.")
    else:
        return s1_it_res


def automox_sentinelone_compare_site_lists(sentinelone_orgname_orgid_dict,automox_orgname_orgid_dict):
    """
    after getting the list of sentinelone and automox's orgname_orgid dicts and:
     1. create two new dicts including only values of sites that are in both systems; will be used for the endpoint comparison later on.
     2. create a dict of sites only found in Automox; for the analyst to review, if necessary.
     3. creates a dict of sites only found in SentinelOne; for the analyst to review, if necessary.
    :return: sentinelone and automox site dicts existing in both platforms, site dict only in automox, site dict only in sentinelone.
    """
    both_platform_automox_site_dict = {}
    both_platform_sentinelone_site_dict = {}
    automox_only_site_dict = {}
    sentinelone_only_site_dict = {}
    for s1_site_name in sentinelone_orgname_orgid_dict.keys(): #we start with the comparison with sentinelone because more clients have s1 only than automox only.
        if s1_site_name in automox_orgname_orgid_dict.keys():
            both_platform_sentinelone_site_dict[s1_site_name] = {"site id" : sentinelone_orgname_orgid_dict[s1_site_name]['site id'], "account id": sentinelone_orgname_orgid_dict[s1_site_name]['account id']}
            both_platform_automox_site_dict[s1_site_name] = automox_orgname_orgid_dict[s1_site_name]['site id']
        else:
            sentinelone_only_site_dict[s1_site_name] = {"site id" : sentinelone_orgname_orgid_dict[s1_site_name]['site id'], "account id": sentinelone_orgname_orgid_dict[s1_site_name]['account id']}
    for automox_site_name in automox_orgname_orgid_dict.keys():
        if automox_site_name not in sentinelone_orgname_orgid_dict.keys():
            automox_only_site_dict[automox_site_name] = automox_orgname_orgid_dict[automox_site_name]['site id']
    return both_platform_sentinelone_site_dict, both_platform_automox_site_dict, sentinelone_only_site_dict, automox_only_site_dict


def sentinelone_create_org_id_dict():
    """
    returns a merged dict of sites from sentinelone. will check if there are additional sites
    that were not included in the first response by the presence of "NextCursor" value.
    :return: merged dict of sites from sentinelone 
    """
    s1_orgid_dict = {}
    s1_res = sentinelone_get_response("sites")
    sentinelone_add_orgid_siteid_to_dict(s1_res, s1_orgid_dict) #add first response to dict from sentinelone
    try:
        s1_pagination = s1_res["pagination"]["nextCursor"]
        while s1_pagination: #adds all requests to the dictionary (if pagination exists).
            s1_res = sentinelone_get_response("sites", {"cursor": s1_pagination})
            sentinelone_add_orgid_siteid_to_dict(s1_res, s1_orgid_dict)
            s1_pagination = s1_res["pagination"]["nextCursor"]
    except NameError:
        print("[*] No pagination was found for sentinelone. skipping...")
    return s1_orgid_dict


def sentinelone_add_orgid_siteid_to_dict(s1_response,orgname_orid_dict):
    """
    support function to add site information from the request to the inserted dict.
    :param s1_response: the response to loop through for site information.
    :param orgname_orid_dict: the dict to which the site infromation will be added to
    :return: None.
    """
    try:
        for site_info in s1_response["data"]["sites"]:
            orgname_orid_dict[site_info["name"]] = {"site id": site_info["id"], "account id": site_info["accountId"]}
    except KeyError:
        pass #error output already configured in the "sentinelone_get_site_list" function.


def sentinelone_create_nested_dict(s1_orgname_orgid_dict):
    """
    performs requests to s1 api for endpoint mac addresses retrieval.
    since we're dealing with two different servers, will first check which one the site belongs to,
     and then perform requests accordingly.
    :param s1_orgname_orgid_dict:
    :return: nested s1 dict with endpoints and mac addresses.
    """
    sentinelone_nested_site_endpoint_dict = {}
    print("[*] Initiating SentinelOne nested dict [*]\n\n")
    for s1_site_name, s1_site_info in s1_orgname_orgid_dict.items():
        temp_endpoint_counter = 0
        print(f"[*] Started collection for the site {s1_site_name}.")
        first_s1_endpoint_res = sentinelone_get_response("agents", {"siteIds": int(s1_site_info["site id"])})
        temp_s1_pagination = first_s1_endpoint_res["pagination"]["nextCursor"]
        sentinelone_nested_site_endpoint_dict[s1_site_name] = {}
        for all_endpoints_info in first_s1_endpoint_res["data"]:
            temp_endpoint_name = all_endpoints_info["computerName"]
            sentinelone_nested_site_endpoint_dict[s1_site_name][temp_endpoint_name] = {"Mac Addresses": []}
            temp_endpoint_counter += 1
            try:
                for network_interfaces in all_endpoints_info["networkInterfaces"]:
                    sentinelone_nested_site_endpoint_dict[s1_site_name][temp_endpoint_name]["Mac Addresses"].append(network_interfaces["physical"])
            except KeyError:
                pass
        while temp_s1_pagination: #loops as long as their more endpoint information to be pulled with other requests
            second_s1_endpoint_res = sentinelone_get_response("agents", {"cursor": temp_s1_pagination, "filteredSiteIds": s1_site_info["site id"] })
            temp_s1_pagination = second_s1_endpoint_res["pagination"]["nextCursor"]
            for all_endpoints_info in second_s1_endpoint_res["data"]:
                temp2_endpoint_name = all_endpoints_info["computerName"]
                sentinelone_nested_site_endpoint_dict[s1_site_name][temp2_endpoint_name] = {"Mac Addresses": []}
                temp_endpoint_counter += 1
                try:
                    for network_interfaces in all_endpoints_info["networkInterfaces"]:
                        sentinelone_nested_site_endpoint_dict[s1_site_name][temp2_endpoint_name]["Mac Addresses"].append(network_interfaces["physical"])
                except KeyError:
                    pass
        print(f"[*] Ended dictionary for site {s1_site_name}. Endpoint amount: {temp_endpoint_counter}")
    print("[+] Nested dictionary for SentinelOne completed. [+]")
    return sentinelone_nested_site_endpoint_dict


def automox_get_response(aut_endpoint_url, aut_req_parameter=dict()):
    """
    assisting function that returns a response of Automox API according to the dynamic values recieved.
    :param aut_endpoint_url: the endpoint suffix we wish to communicate with.
    :param aut_req_parameter: the request parameter we wish to pass with the request.
    :return: the automox request.
    """
    aut_res = requests.get(f'{AUTOMOX_API_URL}{aut_endpoint_url}', headers=AUTOMOX_REQUEST_HEADERS,
                           params=aut_req_parameter)
    return aut_res


def automox_create_org_id_dict():
    """
    creates a dictionary of the organisation id's and names ->
    used to after iterate on all of the automox zones endpoints.
    :return: a dictionary of the organisation id's and names
    """
    automox_orgid_orgname_dict = {}
    res_dict = automox_get_response(f"accounts/{AUTOMOX_ACCOUNT_ID}/zones", {"limit": 100}).json()
    for value in res_dict["data"]:
        automox_orgid_orgname_dict[value["name"]] = {"access key": value["access_key"], "site id": value["organization_id"]}
    return automox_orgid_orgname_dict


def automox_create_nested_dict(automox_orgid_orgname_dict):
    """
    creates a nested dict of automox site, and inside of it dicts of endpoints with endpoint names and mac addresses.
    Since Automox gives the entire api endpoint information in one request, cursor is unnecessary.
    :param automox_orgid_orgname_dict: the dict returned eventually
    :return: the dict returned eventually
    """
    print("[*] Initiating Automox nested dict [*]\n\n")
    automox_nested_site_endpoint_dict = {}
    try:
        for automox_org_name, automox_org_id in automox_orgid_orgname_dict.items():
            print(f"[*] Started collection for the site {automox_org_name}.")
            temp_endpoint_count = 0
            automox_endpoint_res = automox_get_response("servers", {"o": automox_org_id}).json()
            automox_nested_site_endpoint_dict[automox_org_name] = {}  # create a nested dict for the site.
            for endpoint in automox_endpoint_res:
                try:  # if this fails then there are no endpoints in the site - thus its empty. so we skip it.
                    temp_endpoint_name = automox_remove_unecessary_suffix_from_endpoint_name(endpoint["name"])
                    automox_nested_site_endpoint_dict[automox_org_name][temp_endpoint_name] = {"Mac Addresses": []}
                    temp_endpoint_count += 1
                    try:
                        for mac_addresses in endpoint["detail"]["NICS"]:
                            automox_nested_site_endpoint_dict[automox_org_name][temp_endpoint_name]["Mac Addresses"].append(
                                mac_addresses["MAC"])
                    except KeyError: # will occur if there are no mac address for the endpoint, thus something is wrong there.
                        try:
                            automox_insert_endpoint_with_no_status_details_to_dict(endpoint)
                        except:
                            print("[-] A duplicated endpoint was detected, but there was an issue inserting a it to the duplicate endpoint dict.")
                except TypeError:  # skipping empty sites
                    print(f"[*] Detected Automox site with no endpoints: {automox_org_name}.\n skipping...")
            print(f"[*] Finished collection for the site {automox_org_name}. endpoint amount: {temp_endpoint_count} ")

    except:
        print("[-] There was an error reading the automox orgid_orgname dictionary.")
    print("[+] Nested dictionary for Automox completed. [+]")
    return automox_nested_site_endpoint_dict


def automox_remove_duplicated_endpoints(dup_endpoint_dict):
    #TBD - removes duplicated endpoints that are found,
    pass


def automox_insert_endpoint_with_no_status_details_to_dict(endpoint_dict):
    """
    if an endpoint does not have "status details" (and specifically MAC address,
    then it means that it is probably a duplicate (Automox bug that sometimes happen).
    this creates a nested dict with endpoints with the above conditions.
    :param endpoint_dict:
    :return:None
    """
    global automox_duplicate_devices_dict
    temp_device = {"endpoint name": endpoint_dict['name'], "create time": endpoint_dict['create_time'],
                   "organization id": endpoint_dict['organization_id'], "id": endpoint_dict['id']}
    automox_duplicate_devices_dict.update(temp_device)

def automox_remove_unecessary_suffix_from_endpoint_name(automox_endpoint_name):
    """
    removes ".lan" or ".local suffix from endpoint names.
    :param automox_endpoint_name:
    :return: name without suffix.
    """
    if ".local" in automox_endpoint_name:
        automox_endpoint_name = automox_endpoint_name.replace(".local", "")
    elif ".lan" in automox_endpoint_name:
        automox_endpoint_name = automox_endpoint_name.replace(".lan", "")
    else:
        return automox_endpoint_name
    return automox_endpoint_name

def site_dict_to_mac_site_name_dict(site_endpoints_dict):
    """
    support functions: recives dict of endpoint> mac addresses(list) and transforms to mac address: endpoint name dict.
    :param site_endpoints_dict: dictionary of endpoint>mac addresses(list)
    :return:dictionary of mac address>endpoint name
    """
    temp_macaddress_endpoint_name_dict = {}
    for endpoint_name, mac_address_list_array in site_endpoints_dict.items():
        for mac_address_list in mac_address_list_array.values():
            for single_mac_address in mac_address_list:
                if single_mac_address in temp_macaddress_endpoint_name_dict.keys() or single_mac_address == "00:00:00:00:00:00" or len(single_mac_address) == 0: #to avoid unncessecaru loop work.
                    pass
                else:
                    temp_macaddress_endpoint_name_dict[single_mac_address.lower()] = endpoint_name
    return temp_macaddress_endpoint_name_dict


def site_mac_addresses_to_nested_macaddress_siteid_dict(nested_dict):
    """
    recieves the big nested siteid>endpoint name> mac addresses(list) and transforms into nested
    dict of site id>mac address > endpoint name
    :param nested_dict: automox/sentinelone nested dict siteid>endpoint name> mac addresses(list)
    :return: nested dict of site id>mac address > endpoint name
    """
    temp_nested_mac_to_endpoint_dict = {}
    for site_name, site_info in nested_dict.items():
        temp_site_level_dict = site_dict_to_mac_site_name_dict(site_info)
        temp_nested_mac_to_endpoint_dict[site_name] = {}
        temp_nested_mac_to_endpoint_dict[site_name].update(temp_site_level_dict)
    return temp_nested_mac_to_endpoint_dict


def sentinelone_automox_compare_macaddresses_nested_dicts(sentinelone_nested_dict, automox_nested_dict):
    """
    Creates nested dicts to store nested dictionaries per site.
    the outcome is 3 nested dictionary per site, with the comparison based mainly on mac addresses: one for endpoints with mac appearing in both platform
                                                 two for endpoints appearing only in sentinelone
                                                 two for endpoints appearing only in sentinelone
    :param sentinelone_nested_dict:
    :param automox_nested_dict:
    :return:
    """
    both_sites_endpoints_nested_dict = {}
    sentinelone_only_nested_dict = {}
    automox_only_dict_nested_dict = {}
    for site_dict_sentinelone_site_name, site_dict_sentinelone_mac_endpoints_dict in sentinelone_nested_dict.items():
        for site_dict_automox_site_name, site_dict_automox_mac_endpoints_dict in automox_nested_dict.items():
            both_sites_endpoints_dict, sentinelone_site_only_dict, automox_site_only_dict = \
                sentinelone_automox_compare_macaddresses_single_dict\
                    (site_dict_sentinelone_mac_endpoints_dict,site_dict_automox_mac_endpoints_dict)
            if len(both_sites_endpoints_dict) > 0: #add the site only if there's an output (to deny adding empty sites to begin with)
                both_sites_endpoints_nested_dict[site_dict_sentinelone_site_name] = {}
                both_sites_endpoints_nested_dict[site_dict_sentinelone_site_name].update(both_sites_endpoints_dict)
            else:
                continue
            if len(sentinelone_site_only_dict) > 0:
                sentinelone_only_nested_dict[site_dict_sentinelone_site_name] = {}
                sentinelone_only_nested_dict[site_dict_sentinelone_site_name].update(sentinelone_site_only_dict)
            else:
                continue
            if len(automox_site_only_dict) > 0:
                automox_only_dict_nested_dict[site_dict_automox_site_name] = {}
                automox_only_dict_nested_dict[site_dict_automox_site_name].update(automox_site_only_dict)
    updated_both_sites_endpoints_nested_dict, updated_sentinelone_only_nested_dict, updated_automox_only_dict_nested_dict = only_platforms_dict_same_name_falsepositive_remover(both_sites_endpoints_nested_dict,sentinelone_only_nested_dict, automox_only_dict_nested_dict)
    return updated_both_sites_endpoints_nested_dict, updated_sentinelone_only_nested_dict, updated_automox_only_dict_nested_dict


def sentinelone_automox_compare_macaddresses_single_dict(sentinelone_single_site_dict,automox_single_site_dict):
    """
    adds the endpoints to the necessary dict according to a few logic conditions, based mainly on mac addresses.
    logic conditions are: if mac address exists in both dicts, add to both_nested dict.
                          if mac adress only in automox, and the endpoint name is not in both_dict, add to automox_only
                          if mac address only in sentinel and endpoint name not in both_dict.keys(), add to sentinelone_only
    :param sentinelone_single_site_dict: the sentinelone site dict passed from the nested dict.
    :param automox_single_site_dict: the Automox site dict passed from the nested dict.
    :return: endpoints only on Automox
            endpoints only on Sentinelone
            endpoints on both platforms
    """
    both_platforms_endpoints_dict = {}
    only_sentinelone_platform_dict = {}
    only_automox_platform_dict = {}
    for sentinelone_mac_address, sentinelone_endpoint_name in sentinelone_single_site_dict.items():
        if sentinelone_mac_address in automox_single_site_dict.keys(): # and sentinelone_endpoint_name not in both_platforms_endpoints_dict.keys(): #s1 mac is in automox dict, but it's name is not in the both automox platform/
            both_platforms_endpoints_dict[sentinelone_endpoint_name] = {"mac address": sentinelone_mac_address, "Endpoint name in Automox": automox_single_site_dict[sentinelone_mac_address]}
        elif sentinelone_endpoint_name not in both_platforms_endpoints_dict.keys() and sentinelone_mac_address not in automox_single_site_dict.keys():
            only_sentinelone_platform_dict[sentinelone_endpoint_name] = sentinelone_mac_address
        else:
            pass
    for automox_mac_address, automox_endpoint_name in automox_single_site_dict.items():
        automox_endpoint_exists_or_not = automox_name_not_in_both_dict_automox_value(both_platforms_endpoints_dict,automox_endpoint_name)
        if automox_endpoint_exists_or_not is False:
            only_automox_platform_dict[automox_endpoint_name] = automox_mac_address
        else:
            pass
    return both_platforms_endpoints_dict,only_sentinelone_platform_dict,only_automox_platform_dict


def automox_name_not_in_both_dict_automox_value(both_dict,mac_automox_name):
    """
    to deny situations where automox has an mac address that does not exist in sentinelone, this function checks
    if there was already an endpoint name with a dynamic name from Automox already added. returns True if there is one and False if not.
    :param both_dict: the dictionary that holds endpoints that we're detected in both platforms.
    :param mac_automox_name:the automox name that is currently being assesed (if it exists already in the dict or not).
    :return: Bool value
    """
    automox_name_in_dict_count = 0
    for endpoint, site_info in both_dict.items():
        if site_info["Endpoint name in Automox"] == mac_automox_name:
            automox_name_in_dict_count += 1
        else:
            pass
    if automox_name_in_dict_count > 0: #exists already in the dict.
        return True
    return False

def only_platforms_dict_same_name_falsepositive_remover(both_platform_endpoints_dict,sentinel_only_platform_dict, automox_only_platform_dict):
    """
    after the finalization of the dictionaries, this functions goes to the endpoints names, and checks based on them
    if there are similarities between the mac addresses list between the two so called "seperate" endpoints.
     if there are identical, it will add them to the both dict, and remove from the "only" dicts. if not, will keep as is.
    :param sentinel_only_platform_dict:
    :param automox_only_platform_dict:
    :return: new both_platform_endpoint_dict, new only sentinelone dict, new only automox dict.
    """
    global sentinelone_nested_site_endpoint_dict
    to_be_removed_single_and_added_both_dict = {}
    for sentinelone_site_name, sentinelone_site_endpoints in sentinel_only_platform_dict.items():
        for sentinelone_endpoint_name in sentinelone_site_endpoints.keys():
            try:
                sentinelone_comparable_mac_addresses_list = turn_mac_addresses_list_to_lowercase(sentinelone_nested_site_endpoint_dict[sentinelone_site_name][sentinelone_endpoint_name]["Mac Addresses"])
                #sentinelone_comparable_mac_addresses_list = sentinelone_nested_site_endpoint_dict[sentinelone_site_name][sentinelone_endpoint_name]["Mac Addresses"]
                automox_comparable_mac_addresses_list = turn_mac_addresses_list_to_lowercase(automox_nested_site_endpoint_dict[sentinelone_site_name][sentinelone_endpoint_name]["Mac Addresses"])
                #automox_comparable_mac_addresses_list = automox_nested_site_endpoint_dict[sentinelone_site_name][sentinelone_endpoint_name]["Mac Addresses"]
                does_endpoint_share_mac_address = compare_mac_addresses_list_false_positive_remover(sentinelone_comparable_mac_addresses_list, automox_comparable_mac_addresses_list)
                if does_endpoint_share_mac_address is True:
                    if sentinelone_site_name not in to_be_removed_single_and_added_both_dict.keys():
                        to_be_removed_single_and_added_both_dict[sentinelone_site_name] = {"Endpoint Names" :[]}
                        to_be_removed_single_and_added_both_dict[sentinelone_site_name]["Endpoint Names"].append(sentinelone_endpoint_name)
                    elif sentinelone_site_name in to_be_removed_single_and_added_both_dict.keys():
                        to_be_removed_single_and_added_both_dict[sentinelone_site_name]["Endpoint Names"].append(
                            sentinelone_endpoint_name)
                else:
                    pass
            except KeyError:
                pass
    new_both_platform_endpoint_dict, new_sentinel_only_platform_dict, new_automox_only_platform_dict = remove_falsepositives_from_singles_and_add_to_both_dict(sentinel_only_platform_dict,automox_only_platform_dict,both_platform_endpoints_dict,to_be_removed_single_and_added_both_dict)
    return new_both_platform_endpoint_dict, new_sentinel_only_platform_dict, new_automox_only_platform_dict

def remove_falsepositives_from_singles_and_add_to_both_dict(sentinel_only_platform_dict,automox_only_platform_dict,both_platform_endpoints_dict,false_positive_dict):
    """
    second round of endpoint inspection. compares between the only_platform_dicts to see if there are endpoint names that had DIFFERENT mac addresses but they are actually the same pc.
    this function's purpose is to remove these.
    the function iterates over the false_positive_dict, removes the key values from the single platform dicts and add it to the both_platform dict.
    :param sentinel_only_platform_dict: the sentinelone dictionary that includes endpoints that were detected by the first logic as only in sentinelone.
    :param automox_only_platform_dict: the automox dictionary that includes endpoints that were detected by the first logic as only in automox.
    :param both_platform_endpoints_dict: the dictionary that was detected with endpoints that are in both platforms.
    :param false_positive_dict: dictionary passed by the function only_platforms_dict_same_name_falsepositive_remover
    :return: updated dicts after the removal of fp from single platform dicts, and addition to the both platform dict.
    """
    for sentinelone_site_name,sentinelone_endpoint_name_list in false_positive_dict.items():
        for sentinel_endpoint_to_remove in sentinelone_endpoint_name_list.values():
            for sentinel_endpoint_to_remove_str in sentinel_endpoint_to_remove:
                try:
                    del sentinel_only_platform_dict[sentinelone_site_name][sentinel_endpoint_to_remove_str]
                    del automox_only_platform_dict[sentinelone_site_name][sentinel_endpoint_to_remove_str]
                    both_platform_endpoints_dict[sentinelone_site_name][sentinel_endpoint_to_remove_str] = {"mac address": "Based on name",
                                                                                                "Endpoint name in Automox": sentinel_endpoint_to_remove_str}
                except:
                    pass
    return both_platform_endpoints_dict, sentinel_only_platform_dict, automox_only_platform_dict


def compare_mac_addresses_list_false_positive_remover(sentinelone_endpoint_macaddresses_list,automox_endpoint_macadresses_list):
    """
    Turns mac addresses lists into sets and checks if one of them is identical to other.
    :param sentinelone_endpoint_macaddresses_list:
    :param automox_endpoint_macadresses_list:
    :return: Boolean - true - some mac addresses match
                        false - no mac addresses match
    """
    lower_cased_sentinelone_endpoint_macaddresses_list = turn_mac_addresses_list_to_lowercase(sentinelone_endpoint_macaddresses_list)
    lower_cased_automox_endpoint_macaddresses_list = turn_mac_addresses_list_to_lowercase(automox_endpoint_macadresses_list)

    has_similarities_or_not = bool(set(lower_cased_sentinelone_endpoint_macaddresses_list) & set(lower_cased_automox_endpoint_macaddresses_list))
    return has_similarities_or_not


def turn_mac_addresses_list_to_lowercase(mac_address_list):
    """
    turns mac address list to lowercase.
    :param mac_address_list: mac address list to be lowered.
    :return: mac address list with lower cases
    """
    lower_mac_address_list = []
    for mac_address in mac_address_list:
        lower_mac_address_list.append(mac_address.lower())
    return lower_mac_address_list

def remove_empty_dicts_from_final_dicts(nested_dict):
    """
    goes over the final dictionaries and removes empty ones.
    :param nested_dict: given nested dict
    :return: nested dict without empty sites
    """
    site_names_to_be_removed = []
    for site_name, site_dict in nested_dict.items():
        if len(site_dict) == 0:
            site_names_to_be_removed.append(site_name)
    for site_to_be_removed in site_names_to_be_removed:
        del nested_dict[site_to_be_removed]
    return nested_dict


def write_data_to_file(name_prefix, nested_dict):
    """
    writes down data to files
    :param name_prefix: string to be added to the file name (both,sentinel,automox) to differentiate between types
    :param nested_dict: site dict to be written to file
    :return: none.
    """
    try:
        for sitename, siteendpointsinfo in nested_dict.items():
            now = datetime.now()
            current_datetime = now.strftime("%m/%d/%Y, %H:%M:%S")
            file_name = f"{sitename} {name_prefix}.csv"
            for endpoint_name, endpoint_info in siteendpointsinfo.items():
                if name_prefix == "Both Platforms":
                    field_names = ["sentinelone endpoint name", "Sentinelone mac address", "automox endpoint name"]
                    with open(file_name, "a+",encoding="UTF-8",newline='') as csvfile:
                        csvwrite = csv.DictWriter(csvfile, field_names)
                        csvwrite.writeheader()
                        csvwrite.writerow({"sentinelone endpoint name": endpoint_name,
                                           "Sentinelone mac address": endpoint_info["mac address"],
                                           "automox endpoint name": endpoint_info["Endpoint name in Automox"]})

                else:
                    field_names = ["endpoint name", "mac address"]
                    with open(file_name, "a+",encoding="UTF-8",newline='') as csvfile:
                        csvwrite = csv.DictWriter(csvfile, field_names)
                        csvwrite.writeheader()
                        csvwrite.writerow({"endpoint name": endpoint_name,
                                           "mac address": endpoint_info})
    except ValueError as e:
        print(f"[-] An error occured with creating the CSV./skipping...\n error: {e}")
    except KeyError as b:
        print(f"error occured. error: {b}")
#remove 0 length dicts


def calculate_length_final_dicts(both_platform_dict,sentinelone_platform_dict,automox_platform_dict):
    """
    Creates a nested dict with site>dictionary size that can be used to print the general statistics
    :param both_platform_dict: final nested dict with endpoints that include endpoints in both platforms
    :param sentinelone_platform_dict: final nested dict with sentinelone endpoints
    :param automox_platform_dict: final nested dict with automox endpoints
    :return: nested dict with site>dictionary size
    """

    global both_platform_sentinelone_site_dicts
    lengths_nested_dict = {}
    for site_name in both_platform_sentinelone_site_dicts:
        if site_name not in lengths_nested_dict.keys():
            lengths_nested_dict[site_name] = {}
            what_platform, score = length_of_site_from_specific_dict("Both platform",both_platform_dict,site_name)
            lengths_nested_dict[site_name][what_platform] = score
            what_platform1, score1 = length_of_site_from_specific_dict("Sentinelone platform",sentinelone_platform_dict,site_name)
            lengths_nested_dict[site_name][what_platform1] = score1
            what_platform2, score2 = length_of_site_from_specific_dict("Automox platform",automox_platform_dict,site_name)
            lengths_nested_dict[site_name][what_platform2] = score2
        else:
            lengths_nested_dict[site_name] = length_of_site_from_specific_dict("Both platform",both_platform_dict,site_name)
            lengths_nested_dict[site_name] = length_of_site_from_specific_dict("Sentinelone platform",sentinelone_platform_dict,site_name)
            lengths_nested_dict[site_name] = length_of_site_from_specific_dict("Automox platform",automox_platform_dict,site_name)
    return lengths_nested_dict


def length_of_site_from_specific_dict(what_dict_is_this,specific_dict,site_name):
    """
    takes a site dict and calculates its len
    :param what_dict_is_this: the string to be added to the dictionary itself
    :param specific_dict: the dict to calculate len to
    :param site_name: the site's name
    :return: returns len of the dict. if there's no len of the "what dict is this type", it returns it along with the value 0.
    """
    try:
        site_dict_length = len(specific_dict[site_name])
        return what_dict_is_this, site_dict_length
    except KeyError:
        return what_dict_is_this, 0


def write_results_to_files(both_dict,sentinel_dict,automox_dict):
    """
    function that writes data to files
    :param both_dict: both platform dict
    :param sentinel_dict: sentinelone dict
    :param automox_dict: automox dict
    :return:
    """
    write_data_to_file("Both Platforms", both_dict)
    write_data_to_file("Sentinel Only", sentinel_dict)
    write_data_to_file("Automox Only", automox_dict)

def print_score_to_cli(nested_score_dict):
    beginning = '''
####################################################################################################################
Final endpoint amount statistics:
####################################################################################################################
    '''
    print(beginning)
    for site_name, site_statistics in nested_score_dict.items():
        print(f"$ Site name: {site_name}, Both platform endpoint amount: {site_statistics['Both platform']}, Sentinelone only endpoint amount: {site_statistics['Sentinelone platform']}, Automox only endpoint amount: {site_statistics['Automox platform']}")

def main():
    global both_platform_sentinelone_site_dicts
    global sentinelone_nested_site_endpoint_dict
    global automox_nested_site_endpoint_dict
    print(to_print_at_startup)
    automox_orgid_orgname_dict = automox_create_org_id_dict()
    sentinelone_site_dict = sentinelone_create_org_id_dict()
    both_platform_sentinelone_site_dicts, both_platform_automox_site_dict, sentinelone_only_site_dict,\
    automox_only_site_dict = automox_sentinelone_compare_site_lists(sentinelone_site_dict, automox_orgid_orgname_dict)
    sentinelone_nested_site_endpoint_dict = sentinelone_create_nested_dict(both_platform_sentinelone_site_dicts)
    automox_nested_site_endpoint_dict = automox_create_nested_dict(both_platform_automox_site_dict)
    print("[*] Creating nested mac address to endpoint names dictionaries")
    nested_automox_mac_endpointname_dict = site_mac_addresses_to_nested_macaddress_siteid_dict(automox_nested_site_endpoint_dict)
    nested_sentinel_mac_endpointname_dict = site_mac_addresses_to_nested_macaddress_siteid_dict(sentinelone_nested_site_endpoint_dict)
    print("[+] Nested mac address to endpoint names dictionaries complete [+]")
    both_sites_endpoints_dict, sentinelone_site_only_dict, automox_site_only_dict = sentinelone_automox_compare_macaddresses_nested_dicts(
    nested_sentinel_mac_endpointname_dict, nested_automox_mac_endpointname_dict)
    #to add dictionaries counter
    print("[*] Removing empty site dictionaries from final nested dictionaries")
    new_both_sites_endpoints_dict = remove_empty_dicts_from_final_dicts(both_sites_endpoints_dict)
    new_sentinelone_site_only_dict = remove_empty_dicts_from_final_dicts(sentinelone_site_only_dict)
    new_automox_site_only_dict = remove_empty_dicts_from_final_dicts(automox_site_only_dict)
    print("[*] Comparing created dicts for similarities and differences...")
    print("[+] Comparison process complete [+]")
    print("[*] Writing data to file")
    write_results_to_files(new_both_sites_endpoints_dict,new_sentinelone_site_only_dict,new_automox_site_only_dict)
    print("[+]Writing data to file complete [+]")
    lengths_dict = calculate_length_final_dicts(new_both_sites_endpoints_dict,new_sentinelone_site_only_dict,new_automox_site_only_dict)
    print_score_to_cli(lengths_dict)


if __name__ == "__main__":
    main()
