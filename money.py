from abc import ABC, abstractmethod


class Money(ABC):

    @abstractmethod
    def __init__(self, name, amount=None, cost=None):
        """
        :param name: Название валюты
        :param amount: Количество валюты
        :param cost: Стоимость валюты в RUB
        """
        self.name = name.upper()
        self.amount = amount
        self.cost = 1 if self.name == 'RUB' else cost
        self.is_changed = False  # изменился ли курс валюты или ее количество

    def get_cost_in_rubles(self):
        return self.amount * self.cost

    def __str__(self):
        return f"{self.name}: {self.amount}"
