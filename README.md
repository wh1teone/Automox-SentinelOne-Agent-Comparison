# Automox-SentinelOne-Agent-Comparison


This scripts compares the presence of Automox (patch management solution) and Sentinelone (EDR) agents on endpoints.
The comparison is made based on the endpoint's NIC's (or multiple NICS) mac addresses.
The output is three csv files per site:
1.Endpoints that exist in both platforms.
2.Endpoints that exist only in sentinelone.
3.Endpoints that exist only in Automox.

I created this script due to Automox inability to pull the current endpoint's name (populates the endpoint name according to what it was when Automox was installed).
