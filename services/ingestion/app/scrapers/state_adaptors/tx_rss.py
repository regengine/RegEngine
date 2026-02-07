from .generic import GenericRSSScraper

class TexasRegistryScraper(GenericRSSScraper):
    """
    Texas Register scraper.
    Inherits connection logic and RSS parsing from GenericRSSScraper.
    """
    def __init__(self):
        super().__init__(
            feed_url="https://www.sos.state.tx.us/texreg/feed.xml", 
            jurisdiction="US-TX", 
            title_prefix="Texas Register"
        )

