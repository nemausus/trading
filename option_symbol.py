"""
option_symbol.py
~~~~~~~~~~~~~~~~
Parsing and representation of Schwab OCC option symbols.
"""
import datetime

from constants import SCHWAB_TZ


# Standard contract size for equity/index options
OPTION_MULTIPLIER = 100


def is_option(symbol: str) -> bool:
    """Return True if *symbol* looks like an option (>4 characters)."""
    return len(symbol) > 4


def get_option_multiplier(symbol: str) -> int:
    """Return 100 for options, 1 for equities."""
    return OPTION_MULTIPLIER if is_option(symbol) else 1


def base_symbol(symbol: str) -> str:
    """Extract the underlying ticker from an option or equity symbol."""
    return symbol if not is_option(symbol) else symbol.split(' ')[0].rstrip()


def _parse_expiration_date(expiration_date: str) -> datetime.date:
    try:
        dt = datetime.datetime.strptime(expiration_date, '%y%m%d')
        return dt.date()
    except ValueError as e:
        raise ValueError(
            'expiration date must follow format '
            '[two digit year][Month with leading zero]'
            '[Day with leading zero] Found: ' + str(expiration_date)
        ) from e


class OptionSymbol:
    """Parse and represent a Schwab OCC option symbol."""

    def __init__(self, underlying_symbol: str, expiration_date: datetime.date,
                 contract_type: str, strike_price: str):
        self.underlying_symbol = underlying_symbol
        self.expiration_date = expiration_date  # datetime.date
        self.contract_type = contract_type      # 'C' or 'P'
        self.strike_price = strike_price        # decimal string, e.g. "295.00"

    @classmethod
    def parse_symbol(cls, symbol: str) -> 'OptionSymbol':
        """Parse an OCC option symbol string."""
        if not symbol or len(symbol) < 13:
            raise ValueError(f"Invalid option symbol format: {symbol}")

        underlying = symbol[:6].rstrip()
        rest = symbol[6:]

        if 'P' in rest:
            expiration_date_str, strike_str = rest.split('P', 1)
            contract_type = 'P'
        elif 'C' in rest:
            expiration_date_str, strike_str = rest.split('C', 1)
            contract_type = 'C'
        else:
            expiration_date_str, strike_str, contract_type = rest, "1000", 'C'

        try:
            strike = f"{int(strike_str) / 1000.0:.2f}"
        except Exception:
            strike = "0.00"

        return cls(underlying, _parse_expiration_date(expiration_date_str),
                   contract_type, strike)

    def dte(self, ref_date=None) -> int:
        """Days to expiration from *ref_date* (defaults to today in Schwab TZ)."""
        if ref_date is None:
            ref_date = datetime.datetime.now(SCHWAB_TZ).date()
        elif isinstance(ref_date, str):
            ref_date = datetime.date.fromisoformat(ref_date[:10])
        return int((self.expiration_date - ref_date).days)
