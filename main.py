import argparse
import asyncio

import aiohttp

from money import Money

URL_XML = "https://www.cbr-xml-daily.ru/daily_utf8.xml"
URL_JSON = 'https://www.cbr-xml-daily.ru/daily_json.js'


class Currency(Money):
    def __init__(self, name, amount=None):
        Money.__init__(self, name, amount)


async def repeat(interval, func, *args, **kwargs):
    while True:
        await asyncio.gather(
            func(*args, **kwargs),
            asyncio.sleep(interval)
        )


async def fetch_exchange_rates(**kwargs):
    currency_objs_list = kwargs.get('currency_objs_list')
    if currency_objs_list is None or not currency_objs_list:
        return
    async with aiohttp.ClientSession() as session:
        async with session.get(URL_JSON, allow_redirects=True, ssl=False) as response:
            json_data = await response.json(content_type='application/javascript')
            for currency_obj in currency_objs_list:
                try:
                    parsed_valute_cost = json_data['Valute'][currency_obj.name.upper()]['Value']
                except:
                    ### удаляем валюту, если такой не существует
                    currency_objs_list.remove(currency_obj)
                    del currency_obj
                if parsed_valute_cost != currency_obj.cost:  ## если курс изменился
                    currency_obj.is_changed = True
                    currency_obj.cost = parsed_valute_cost


async def check_changes(**kwargs):
    currency_objs_list = kwargs.get('currency_objs_list')
    for currency_obj in currency_objs_list:
        if currency_obj.is_changed:
            currency_obj.is_changed = False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--period', action="store", dest="period", required=True, type=int,
                        help='update period in minutes')
    parser.add_argument('--debug', dest="debug", default=False,
                        type=lambda x: (str(x).lower() in ['true', '1', 'y', 'yes']),
                        help='debug enable mode')
    parser.add_argument('--rub', action="store", dest="rub", type=float, help='rub currency amount')
    parser.add_argument('--usd', action="store", dest="usd", type=float, help='usd currency amount')
    parser.add_argument('--eur', action="store", dest="eur", type=float, help='eur currency amount')
    parsed_script_args = parser.parse_args()
    parsed_script_args_dict = parsed_script_args.__dict__

    rub = Currency(name='rub', amount=parsed_script_args.rub)
    usd = Currency(name='usd', amount=parsed_script_args.usd)
    eur = Currency(name='eur', amount=parsed_script_args.eur)

    loop = asyncio.get_event_loop()
    tasks = [
        loop.create_task(
            repeat(parsed_script_args.period * 60, fetch_exchange_rates, currency_objs_list=[usd, eur])
        ),
        loop.create_task(
            repeat(60, check_changes, currency_objs_list=[rub, usd, eur])
        )

    ]
    loop.run_until_complete(asyncio.gather(*tasks))
    loop.close()
