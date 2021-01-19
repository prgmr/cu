import argparse
import asyncio
import logging
import sys
from itertools import combinations

import aiohttp
import requests
from aiohttp import web

from money import Money

URL_JSON = 'https://www.cbr-xml-daily.ru/daily_json.js'

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


class Currency(Money):
    def __init__(self, name, amount=None):
        Money.__init__(self, name, amount)


def check_for_alive_url(url):
    r = requests.head(url)
    return r.status_code == 200


async def repeat(interval, func, *args, **kwargs):
    while True:
        await asyncio.gather(
            func(*args, **kwargs),
            asyncio.sleep(interval)
        )


async def fetch_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json(content_type='application/javascript')


async def fetch_exchange_rates(**kwargs):
    currency_objs_list = kwargs.get('currency_objs_list')
    if currency_objs_list is None or not currency_objs_list:
        return
    json_data = await fetch_url(URL_JSON)
    if not json_data:
        logger.critical(f"No data from {URL_JSON}")
        return
    logging.info(f"Successful fetch data from {URL_JSON}")
    for currency_obj in currency_objs_list:
        try:
            parsed_valute_cost = json_data['Valute'][currency_obj.name.upper()]['Value']
        except:
            ### удаляем валюту, если такой не существует
            currency_objs_list.remove(currency_obj)
            del currency_obj
        else:
            if currency_obj.cost is None:  ## меняем первоначальное состояние
                currency_obj.cost = parsed_valute_cost
                continue
            if parsed_valute_cost != currency_obj.cost:  ## если курс изменился
                currency_obj.is_changed = True
                currency_obj.cost = parsed_valute_cost
                logger.info(f"New exchange rate for {currency_obj.name} is {parsed_valute_cost}")


async def check_changes(**kwargs):
    currency_objs_list = kwargs.get('currency_objs_list')
    for currency_obj in currency_objs_list:
        if currency_obj.is_changed:
            logger.info(f"{currency_obj.name} is changed amount or exchange rate")
            currency_obj.is_changed = False


routes = web.RouteTableDef()


@routes.get('/')
async def index(request):
    currency_objs_list = request.app['currency_objs_list']
    response = ''
    for currency_obj in currency_objs_list:
        response += f"GET http://{request.host}/{currency_obj.name}/get\n"
    response += f"GET http://{request.host}/amount/get\n"
    response += f"POST http://{request.host}/amount/set\n"
    response += f"POST http://{request.host}/modify\n"
    return web.Response(text=response)


@routes.get('/amount/get')
async def get_amount(request):
    currency_objs_list = request.app['currency_objs_list']
    total_cost_in_rubles = sum(
        list(map(lambda x: x.get_cost_in_rubles(), currency_objs_list)))  ## сумма всех валют в рублях
    response_string = ""
    total_cost_by_currency_list = []
    for currency_obj in currency_objs_list:
        response_string += f"{currency_obj.name}: {currency_obj.amount}\n"
        total_cost_by_currency_list.append(f"{round(total_cost_in_rubles / currency_obj.cost, 2)} {currency_obj.name}")
    response_string += '\n'
    for objs_tuple in combinations(currency_objs_list, 2):  ## ищем комбинации по 2 элемента
        response_string += f"{objs_tuple[0].name}-{objs_tuple[1].name}: {round(objs_tuple[1].cost / objs_tuple[0].cost, 2)}\n"

    response_string += f"\nsum: / " + " / ".join(total_cost_by_currency_list)
    logger.debug(f"{request.path} response={response_string}")
    return web.Response(text=response_string, content_type='text/plain')


@routes.get('/{currency_name}/get')
async def get_currency_name(request):
    req_currency_name = request.match_info['currency_name'].upper()
    currency_objs_list = request.app['currency_objs_list']
    current_currency = next(filter(lambda x: x.name == req_currency_name, currency_objs_list), None)
    if current_currency is None:
        return web.Response(text=f'Unknown currency: {req_currency_name}', status=403)
    response = {
        "Currency": current_currency.name,
        "Amount": current_currency.amount,
        "Cost": current_currency.cost
    }
    logger.debug(f"request={request.path} response={response}")
    return web.json_response(response)


@routes.post('/amount/set')
async def set_amount(request):
    request_body = await request.json()
    if not request_body:
        logger.warning(f"{request.path}:{request_body} Unknown request")
        return web.Response(text=f'Unknown request', status=403)
    currency_objs_list = request.app['currency_objs_list']
    response = {}
    for key, value in request_body.items():
        for currency_obj in currency_objs_list:
            if key.upper() == currency_obj.name:
                currency_obj.amount = value
                currency_obj.is_changed = True

    for currency_obj in currency_objs_list:
        response[currency_obj.name] = currency_obj.amount

    logger.debug(f"request={request.path}:{request_body} response={response}")
    return web.json_response(response)


@routes.post('/modify')
async def set_amount(request):
    request_body = await request.json()
    if not request_body:
        logger.warning(f"{request.path}:{request_body} Unknown request")
        return web.Response(text=f'Unknown request', status=403)
    currency_objs_list = request.app['currency_objs_list']
    response = {}
    for key, value in request_body.items():
        for currency_obj in currency_objs_list:
            if key.upper() == currency_obj.name:
                currency_obj.amount += value
                currency_obj.is_changed = True

    for currency_obj in currency_objs_list:
        response[currency_obj.name] = currency_obj.amount

    logger.debug(f"request={request.path}:{request_body} response={response}")
    return web.json_response(response)


def get_webserver_settings(**kwargs):
    app = aiohttp.web.Application()
    app['currency_objs_list'] = kwargs.get('currency_objs_list')
    app.add_routes(routes)
    return app


if __name__ == '__main__':
    script_arguments_list = sys.argv
    catched_currencies_list = list(
        filter(lambda x: len(x) == 5 and x.startswith('--') and x[2:].isalpha(), script_arguments_list))

    parser = argparse.ArgumentParser()
    parser.add_argument('--period', action="store", dest="period", required=True, type=int,
                        help='update period in minutes')
    parser.add_argument('--debug', dest="debug", default=False,
                        type=lambda x: (str(x).lower() in ['true', '1', 'y', 'yes', 'on']),
                        help='debug enable mode')
    for currency_arg in catched_currencies_list:
        cur_name = currency_arg[2:]
        parser.add_argument(currency_arg, action="store", dest=cur_name, type=float, help=f'{cur_name} currency amount')

    parsed_script_args = parser.parse_args()
    parsed_script_args_dict = parsed_script_args.__dict__

    if parsed_script_args.debug:
        logger.setLevel(level=logging.DEBUG)

    logger.info(f'Application started with params {parsed_script_args_dict}')
    logger.debug('Debug enabled')

    currency_objs_list = []
    for currency_arg in catched_currencies_list:
        cur_name = currency_arg[2:]
        currency_objs_list.append(Currency(name=cur_name, amount=parsed_script_args_dict[cur_name]))
    currency_objs_list_without_RUB = list(filter(lambda x: x.name != 'RUB', currency_objs_list))

    url = URL_JSON
    if not check_for_alive_url(url):
        logger.critical(f"ping {url} fail")
        sys.exit(1)

    loop = asyncio.get_event_loop()
    tasks = [
        loop.create_task(
            repeat(parsed_script_args.period * 60, fetch_exchange_rates,
                   currency_objs_list=currency_objs_list_without_RUB)
        ),
        loop.create_task(
            repeat(60, check_changes, currency_objs_list=currency_objs_list)
        ),
        loop.create_task(
            web.run_app(get_webserver_settings(currency_objs_list=currency_objs_list), host='127.0.0.1', port=8000)
        )

    ]
    loop.run_until_complete(asyncio.gather(*tasks))
    loop.close()
