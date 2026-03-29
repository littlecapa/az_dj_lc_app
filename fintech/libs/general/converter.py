from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

def string2dec(price):
    """Convert a string to a Decimal, handling German format."""
    logger.info(f"Convert {price} to Decimal")
    string = str(price)
    try:
        if "," in string:  # Check for potential German format
            parts = string.split(",")
            if len(parts) == 2:  # Ensure only one comma (decimal separator)
                integer_part = parts[0].replace(".", "")  # Remove thousands separators from integer part
                decimal_part = parts[1]
                if decimal_part.find(".") != -1:  # Check for invalid decimal separator
                    logger.error(f"Invalid decimal string: {string} {price}")
                    raise ValueError(f"Invalid decimal string: {string}")   
                string = f"{integer_part}.{decimal_part}"  # Combine with "." as decimal
            else:  # More or less than one comma is an invalid format.
                logger.error(f"Invalid decimal string: {string} {price}")
                raise ValueError(f"Invalid decimal string: {string}")
        return Decimal(string)
    except ValueError:
        logger.error(f"Invalid decimal string: {string} {price}")
        raise ValueError(f"Invalid decimal string: {string}")