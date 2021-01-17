import argparse
from money import Money


class Currency(Money):
    def __init__(self, name, amount=None):
        Money.__init__(self, name, amount)


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
