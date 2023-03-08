from retrying import retry
import requests
import osmnx as ox

ox.config(timeout=10000, use_cache=False) #timeout means the timeout interval for the http request and for API to use while running the query. 

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning) #avoiding a certain class for warnings. 

from .config import roads_cat
import logging #tracking events when the software runs. 
logger= logging.getLogger(__name__) #This means that logger names track the package/module hierarchy, and it’s intuitively obvious where events are logged just from the logger name.

def is_connection_error(exception):
    
    logger.error("Connection error raised. Retry...")
    return isinstance(exception, requests.exceptions.ConnectionError)

#This is a function to extract the boundary based on a name.
@retry(
    wait_fixed=20000, stop_max_attempt_number=10, retry_on_exception=is_connection_error
) #retry in case of failure, for instance internet failure.
def getting_boundary_from_osmnx(name):
    return ox.geocode_to_gdf(name, by_osmid=False) #geocode to geodataframe.

#This is a function to extract the boundary base on an OSM ID 
@retry(
    wait_fixed=20000, stop_max_attempt_number=10, retry_on_exception=is_connection_error
)

def getting_boundary_from_id(id):
    return ox.geocode_to_gdf(id, by_osmid=True)# by_osmid=True. In this case, geocode_to_gdf treats the query argument as an OSM ID (or list of OSM IDs) for Nominatim lookup rather than text search


#This is a function to obtain geometries in a given polygon??? The roads already???
@retry(
    wait_fixed=20000, stop_max_attempt_number=10, retry_on_exception=is_connection_error
)

def getting_data_from_osmnx(boundary):

    "This is a  function to extract the geometries from a polygon"
    try:
        data = ox.geometries_from_polygon(boundary, {"highway": roads_cat})#creates a GeoDataframe of OSM entities withihn boundaries of a multipolygon. Parameteres, polygon and tags. 
        #Boundary = has to be a polygon.
        #Roads cat = main_roads_cat + local_roads_cat + active_roads_cat defined in the config.py

        return data
    except requests.exceptions.Timeout as timeout:
        logger.error("triggered a timeout.")
        return "timeout_error"

    except requests.exceptions.ConnectionError as conn_error:
        logger.error("Failed due to a connection error after 10 attempts.\n%s", conn_error)
        return "connection_error"

    # FIXME for Arnaud: can we make sure we only get ways here? (ox.geometries only takes two parameters)
    # Arnaud : According to the doc, we cannot specify the type of geometry we want from the geometries_from_polygon
