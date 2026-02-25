from ClientManager import ClientManager
from PluginManager import loadPlugins
import argparse
import json
import re
import threading
import time

VERSION_PATH = "Resources/version.txt"
EQUIP_PATH = "Resources/equip.xml"


def _strip_json_comments(raw):
    """Remove // and /* */ comments from JSON-like text."""
    no_block = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    return re.sub(r"//[^\n\r]*", "", no_block)


def load_accounts(path="Accounts.json"):
    try:
        with open(path, "r", encoding="utf-8") as file:
            raw = file.read()
    except IOError:
        print("Missing Accounts.json file")
        return None

    # Try strict JSON first.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: accept comments like in Accounts_ex.json examples.
    try:
        return json.loads(_strip_json_comments(raw))
    except json.JSONDecodeError as e:
        print(f"Invalid Accounts.json at line {e.lineno}, column {e.colno}: {e.msg}")
        print("Hint: use valid JSON (double quotes, no trailing commas).")
        return None


def main():
    parser = argparse.ArgumentParser(description="pyrelay")
    parser.add_argument("-s", "--servers", action="store_true", help="Update the server ips")

    args = parser.parse_args()
    accounts = load_accounts("Accounts.json")
    if accounts is None:
        return 1

    loadPlugins()
    clientMan = ClientManager()

    if args.servers:
        clientMan.updateServers = True

    account_threads = []
    for account in accounts:
        thread = threading.Thread(target=clientMan.addClient, args=(account,))
        thread.daemon = True
        thread.start()
        account_threads.append(thread)

    for thread in account_threads:
        thread.join()

    try:
        while 1:
            if clientMan.reconnectIfNeeded():
                print("No clients are active - exiting")
                break
            time.sleep(0.5)
    except (KeyboardInterrupt, SystemExit):
        clientMan.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
