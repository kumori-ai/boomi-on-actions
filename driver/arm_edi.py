"""B2B/EDI: a trading partner as code.

Creates one X12 trading partner with invented details through the Platform API, reads it back, finds it with a
query, deletes it, and confirms the same query no longer finds it. Nothing is deployed, so no trading-partner
license is used. Nothing runs on the runner here except these HTTPS calls.
"""
import sys
from boomi_api import call, licenses_used
from demo_report import finish, step

NAME = '[GHA TEST] Penny Paperclip Stationers (X12)'
blank = dict.fromkeys(('address1', 'address2', 'city', 'contactName', 'country', 'email', 'fax', 'phone', 'postalcode', 'state'), '')
BODY = {'componentName': NAME, 'standard': 'x12', 'classification': 'tradingpartner', 'folderName': 'Runner tests',
        'ContactInfo': dict(blank, contactName='Penny Paperclip', city='Staplerton'),
        'PartnerInfo': {'X12PartnerInfo': {'X12ControlInfo': {'ISAControlInfo': {'interchangeIdQualifier': 'X12IDQUAL_ZZ', 'interchangeId': 'PAPERCLIP'},
                                                              'GSControlInfo': {'applicationcode': 'PAPERCLIP'}}}},
        'PartnerCommunication': {}, 'PartnerDocumentTypes': {}}


def find():
    # the query takes 'name' only with LIKE (measured 2026-10-10)
    code, d = call('POST', 'TradingPartnerComponent/query', {'QueryFilter': {'expression': {'operator': 'LIKE', 'property': 'name', 'argument': ['%Penny Paperclip%']}}})
    return code, [r for r in d.get('result', []) if not r.get('deleted')] if code == 200 else []


def main():
    code, left = find()
    for old in left: call('DELETE', f"TradingPartnerComponent/{old.get('componentId')}")
    lic = licenses_used()
    step('baseline', 'Read the account before touching it', leftovers_removed=len(left), trading_partner_licenses_in_use=lic.get('tradingPartner', 0) + lic.get('tradingPartnerTest', 0))
    code, made = call('POST', 'TradingPartnerComponent', BODY)
    pid = made.get('componentId') if code == 200 else None
    if not step('create', 'Created an X12 trading partner with one API call (invented company: Penny Paperclip Stationers)', 'done' if pid else 'failed', http=code,
                reason=str(made.get('message') or '')[:160] or None):
        return False
    ok = True
    try:
        code, got = call('GET', f'TradingPartnerComponent/{pid}')
        isa = (((got.get('PartnerInfo') or {}).get('X12PartnerInfo') or {}).get('X12ControlInfo') or {}).get('ISAControlInfo') or {}
        ok &= step('read', 'Read it back: the interchange id survived the round trip', 'done' if isa.get('interchangeId') == 'PAPERCLIP' else 'failed', standard=got.get('standard'), interchange_id=isa.get('interchangeId'))
        code, rows = find()
        ok &= step('find', 'Found it with a query, the way a pipeline would look one up', 'done' if len(rows) == 1 else 'failed', matches=len(rows))
    finally:
        code = call('DELETE', f'TradingPartnerComponent/{pid}')[0]
        gone = call('GET', f'TradingPartnerComponent/{pid}')[1].get('deleted')
        _, rows = find()
        ok &= step('deleted', 'Deleted it, and the same query now finds nothing', 'done' if code == 200 and gone and not rows else 'failed', http=code, still_found=len(rows))
        lic = licenses_used()
        ok &= step('clean', 'No license was used: nothing was deployed', trading_partner_licenses_in_use=lic.get('tradingPartner', 0) + lic.get('tradingPartnerTest', 0))
    return ok


if __name__ == '__main__':
    ok = False
    try:
        ok = bool(main())
    except Exception as e:
        step('crashed', 'The script stopped on an error', 'failed', error=f'{type(e).__name__}: {e}'[:160])
    finally:
        finish(ok, 'A trading partner was created, read, found and deleted through the API' if ok else 'The run did not hold: see the failed step')
    sys.exit(0 if ok else 1)
