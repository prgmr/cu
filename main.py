import argparse
import asyncio
import logging

import aiohttp
from aiohttp import web

from money import Money

URL_XML = "https://www.cbr-xml-daily.ru/daily_utf8.xml"
URL_JSON = 'https://www.cbr-xml-daily.ru/daily_json.js'

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


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
                if currency_obj.cost is None:  ## меняем первоначальное состояние
                    currency_obj.cost = parsed_valute_cost
                    return
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
    return web.json_response({"status": "OK"})


@routes.get('/amount/get')
async def get_amount(request):
    currency_objs_list = request.app['currency_objs_list']
    total_cost_in_rubles = sum(list(map(lambda x: x.get_cost_in_rubles(), currency_objs_list)))
    ### TODO: переделать без множества циклов
    ### TODO: добавить rub-usd....
    response_string = ""
    for currency_obj in currency_objs_list:
        response_string += f"{currency_obj.name}: {currency_obj.amount}\n"
    response_string += f"sum: "
    for currency_obj in currency_objs_list:
        response_string += f"/ {round(total_cost_in_rubles / currency_obj.cost, 2)} {currency_obj.name}"
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

    if parsed_script_args.debug:
        logger.setLevel(level=logging.DEBUG)

    logger.info(f'Application started with params {parsed_script_args.__dict__}')
    logger.debug('Debug enabled')

    rub = Currency(name='rub', amount=parsed_script_args.rub)
    usd = Currency(name='usd', amount=parsed_script_args.usd)
    eur = Currency(name='eur', amount=parsed_script_args.eur)

    loop = asyncio.get_event_loop()
    tasks = [
        loop.create_task(
            ### TODO: переделать на wait_for с timeout
            repeat(parsed_script_args.period * 60, fetch_exchange_rates, currency_objs_list=[usd, eur])
        ),
        loop.create_task(
            repeat(60, check_changes, currency_objs_list=[rub, usd, eur])
        ),
        loop.create_task(
            web.run_app(get_webserver_settings(currency_objs_list=[rub, usd, eur]), host='127.0.0.1', port=8000)
        )

    ]
    loop.run_until_complete(asyncio.gather(*tasks))
    loop.close()
