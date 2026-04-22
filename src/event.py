class Event(object):
    """
    Event is base class providing an interface for all subsequent 
    (inherited) events, that will trigger further events in the 
    trading infrastructure.
    """
    pass

class MarketEvent(Event):
    """
    Handles the event of receiving a new market update with 
    corresponding bars.
    """
    def __init__(self):
        self.type = 'MARKET'

class SignalEvent(Event):
    """
    Handles the event of sending a Signal from a Strategy object.
    This is received by a Portfolio object and acted upon.
    """
    def __init__(self, symbol, datetime, signal_type, strength=1.0):
        """
        Parameters:
        symbol - The symbol for the signal (e.g. 'IF').
        datetime - The timestamp at which the signal was generated.
        signal_type - 'LONG' or 'SHORT' or 'EXIT'.
        strength - Optional strength field for scaling trades.
        """
        self.type = 'SIGNAL'
        self.symbol = symbol
        self.datetime = datetime
        self.signal_type = signal_type
        self.strength = strength

class OrderEvent(Event):
    """
    Handles the event of sending an Order to an execution system.
    The order contains a symbol (e.g. 'IF'), a type (market or limit),
    quantity and a direction.
    """
    def __init__(self, symbol, order_type, quantity, direction):
        """
        Parameters:
        symbol - The instrument to trade.
        order_type - 'MKT' (Market) or 'LMT' (Limit).
        quantity - Non-negative integer for quantity.
        direction - 'BUY' or 'SELL'.
        """
        self.type = 'ORDER'
        self.symbol = symbol
        self.order_type = order_type
        self.quantity = quantity
        self.direction = direction

    def print_order(self):
        """
        Outputs the values within the Order.
        """
        print(f"Order: Symbol={self.symbol}, Type={self.order_type}, Quantity={self.quantity}, Direction={self.direction}")

class FillEvent(Event):
    """
    Encapsulates the notion of a Filled Order, as returned
    from a brokerage. Stores the quantity of an instrument
    actually filled and at what price. Also stores the commission
    of the trade from the brokerage.
    """
    def __init__(self, timeindex, symbol, exchange, quantity, 
                 direction, fill_cost, commission=None):
        """
        Parameters:
        timeindex - The bar-resolution when the order was filled.
        symbol - The instrument which was filled.
        exchange - The exchange where the order was filled.
        quantity - The filled quantity.
        direction - The direction of fill ('BUY' or 'SELL').
        fill_cost - The holdings value in terms of the fill price.
        commission - An optional commission sent from brokerage.
        """
        self.type = 'FILL'
        self.timeindex = timeindex
        self.symbol = symbol
        self.exchange = exchange
        self.quantity = quantity
        self.direction = direction
        self.fill_cost = fill_cost

        # Calculate commission
        if commission is None:
            self.commission = self.calculate_ib_commission()
        else:
            self.commission = commission

    def calculate_ib_commission(self):
        """
        Placeholder for commission calculation.
        In this project, we use 0.0002 as specified in the plan.
        """
        # Note: fill_cost is quantity * price
        # We handle this in Execution or Portfolio usually, 
        # but following basic event-driven structure:
        return 0.0002 * self.fill_cost
