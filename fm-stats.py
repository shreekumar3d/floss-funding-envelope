#!/usr/bin/env python3
#
# fm-stats
#
# Extract and dump useful stats from funding-manifest.csv file
#

import csv
import datetime
import dateutil.parser
import time
import json
from pprint import pprint
import math
import argparse

# FLOSS fund is looking to fund entities in the range
# 10k - 100k.
ft = 10000  # 10k USD min

# Currency conversion as of 26 Nov 2024
# This isn't correct either for the past, or for
# the future, but it's a good enough approximation for now
currency_weight = {
    "USD": 84.31,
    "EUR": 88.59,
    "CAD": 59.76,
    "INR": 1,
}


def dtformat(dt):
    return dt.strftime("%a, %-d %b %Y %H:%M:%S %Z")


parser = argparse.ArgumentParser()
parser.add_argument(
    "manifest", metavar="funding-manifest.csv", help="Path to funding-manifest.csv"
)
args = parser.parse_args()

csvfile = open(args.manifest, encoding="utf-8")
reader = csv.reader(csvfile)
nr = 0
disabled = 0
errors = 0
mdesc = []
meets_ft = 0
manifests_zfr = 0  # zero fund requested !
etype_count = {}
etype_meets_ft = {}
erole_count = {}
etype_proj_count = {}
etype_max_fr = {}
lic_map = {}
annual_fin_totals = {}
fh_currencies = {}

ft_keys = ["income", "expenses", "taxes"]
manifest_fin_count = {
    "income": 0,
    "expenses": 0,
    "taxes": 0,
}
for idx, row in enumerate(reader):
    if idx == 0:
        continue
    nr += 1
    rid, url, created_at, updated_at, status, manifest_json = row
    if status != "active":
        disabled += 1
        continue
    try:
        manifest = json.loads(manifest_json)
    except json.decoder.JSONDecodeError as err:
        print(f"At row={rid}, error:{err}")
        errors += 1
        continue

    created_at = dateutil.parser.parse(created_at, fuzzy=True)
    updated_at = dateutil.parser.parse(updated_at, fuzzy=True)

    this_mdesc = {
        "id": rid,
        "url": url,
        "created_at": created_at,
        "updated_at": updated_at,
        "updated_at": updated_at,
        "manifest": manifest,
    }
    for prj in manifest["projects"]:
        for lic in prj["licenses"]:
            # NOTE: potential validation bug
            # one project has a misspelled "sdpx" rather than "spdx"
            if lic.startswith("spdx:") or lic.startswith("sdpx:"):
                lic = lic[5:]
            if lic in lic_map:
                lic_map[lic] += 1
            else:
                lic_map[lic] = 1
    # print(json.dumps(manifest, indent=2))
    plan_max = {}
    for plans in manifest["funding"]["plans"]:
        freq = plans["frequency"]
        amount = plans["amount"]
        if freq in plan_max:
            plan_max[freq] = max(plan_max[freq], amount)
        else:
            plan_max[freq] = amount
    max_fr = 0
    if "one-time" in plan_max:
        max_fr = max(plan_max["one-time"], max_fr)
    if "monthly" in plan_max:
        max_fr = max(plan_max["monthly"] * 12, max_fr)
    if "yearly" in plan_max:
        max_fr = max(plan_max["yearly"], max_fr)
    plan_max["max_fr"] = max_fr
    if max_fr >= ft:
        meets_ft += 1
    this_mdesc["funding-plan-max"] = plan_max
    mdesc.append(this_mdesc)

    # Update stats
    etype = manifest["entity"]["type"]
    if etype in etype_count:
        etype_count[etype] += 1
        etype_proj_count[etype] += len(manifest["projects"])
        etype_max_fr[etype] = max(etype_max_fr[etype], max_fr)
    else:
        etype_count[etype] = 1
        etype_proj_count[etype] = len(manifest["projects"])
        etype_max_fr[etype] = max_fr

    if max_fr >= ft:
        if etype in etype_meets_ft:
            etype_meets_ft[etype] += 1
        else:
            etype_meets_ft[etype] = 1

    erole = manifest["entity"]["role"]
    if erole in erole_count:
        erole_count[erole] += 1
    else:
        erole_count[erole] = 1

    fin_totals = {
        "income": 0,
        "expenses": 0,
        "taxes": 0,
    }
    if "history" in manifest["funding"] and manifest["funding"]["history"]:
        for hist in manifest["funding"]["history"]:
            year = hist["year"]
            if year not in annual_fin_totals:
                annual_fin_totals[year] = {
                    "income": 0,
                    "expenses": 0,
                    "taxes": 0,
                }
            # Normalize fin totals to USD, as the FLOSS fund gives >= $$$$$ !
            c_weight = (
                currency_weight[hist["currency"]] / currency_weight["USD"]
            )  # required field
            for key in ft_keys:
                if key in hist:
                    value = hist[key] * c_weight
                    annual_fin_totals[year][key] += value
                    fin_totals[key] += value
            fh_currencies[hist["currency"]] = 1
        for key in ft_keys:
            if fin_totals[key] > 0:
                manifest_fin_count[key] += 1
            fin_totals[key] = math.floor(fin_totals[key])
    this_mdesc["fin_totals"] = fin_totals

    if max_fr == 0:
        manifests_zfr += 1

fin_totals = {
    "income": 0,
    "expenses": 0,
    "taxes": 0,
}

for year in annual_fin_totals:
    for key in ft_keys:
        value = math.floor(annual_fin_totals[year][key])
        annual_fin_totals[year][key] = value
        fin_totals[key] += value

mdesc.sort(key=lambda x: x["funding-plan-max"]["max_fr"], reverse=True)
print(f"Total manifests = {nr} Disabled = {disabled} Errors = {errors}")
print(f"Manifests above funding threshold = {meets_ft}")
print(f"Manifests requesting NO SPECIFIC (0) funding = {manifests_zfr}")
print("Cumulative financials for all years reported in manifests:")
pprint(fin_totals)
print("Entity Role:")
print(erole_count)
print("Entity Type:")
print(etype_count)
print("Projects per Entity Type:")
print(etype_proj_count)
print("Requested Max funding per Entity Type:")
print(etype_max_fr)
print("Above threshold manifests per Entity Type:")
print(etype_meets_ft)
print("Licenses:")
pprint(lic_map)
print("Annual Financial Totals:")
pprint(annual_fin_totals)
print("Finances Reported by entities:")
pprint(manifest_fin_count)
print("Currencies:", list(fh_currencies.keys()))
print()
print(f"-- Manifests above funding threshold {ft//1000}k USD --")
print()
for idx, minfo in enumerate(mdesc):
    if idx == meets_ft:
        print()
        print(f"-- Manifests below funding threshold {ft//1000}k USD --")
        print()
    created_at = minfo["created_at"]
    updated_at = minfo["updated_at"]
    mf = minfo["funding-plan-max"]["max_fr"]
    manifest = minfo["manifest"]
    print(idx + 1, minfo["url"])
    print("  Entity Type : ", manifest["entity"]["type"])
    print("  Max funding requested : ", mf)
    print("  Financial totals: ", minfo["fin_totals"])
    print("  Created:", dtformat(created_at))
    if created_at != updated_at:
        diff = updated_at - created_at
        print("  Updated:", dtformat(updated_at), f"({diff})")