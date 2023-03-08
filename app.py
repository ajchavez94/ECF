from src.preprocess import process_all, process_country, process_nuts
from src.utils import merge_gdf

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log", 'w', 'utf-8'),
        logging.StreamHandler()
    ]
)
logging._defaultFormatter = logging.Formatter(u"%(message)s")

logger= logging.getLogger(__name__)

if __name__=="__main__":
    try:
        process_all()
        # process_country("Italy")
        # process_nuts()
        # split_gdf('data/NUTS/nuts3-2021.gpkg', 'data/NUTS/nuts3_by_country/', 'CNTR_CODE')
        # merge_gdf('outputs/cyclenetworks/NL/', '-cycle_network.gpkg', 'outputs/cyclenetworks/NL-cycle_network.gpkg')
    except Exception:
        logger.critical('An error occured during the run:', exc_info=True)
        #sys.exit()
 