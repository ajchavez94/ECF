import os
from fiona import bounds
import geopandas as gpd
import datetime
import requests

#calls functions created in scripts
from .utils import create_dir_if_needed, diacritics_to_ascii, calc_area_info
from .config import nominatim_dir, gis_file_ext, datetime_format
from .osmnx import getting_boundary_from_id, getting_boundary_from_osmnx

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import logging

logger = logging.getLogger(__name__)


def get_boudaries_id_names(function, name, **params):
    path = params.get("path")
    name_or_id = params.get("id", name)
    nb_downloaded = params.get("nb_downloaded") #what are the nb dowloaded
    nb_skipped = params.get("nb_skipped") 
    nb_failed = params.get("nb_failed")
    country_ascii = params.get("country_ascii")
    country = params.get("country")
    full_name = country_ascii + "/" + diacritics_to_ascii(name)
    path = nominatim_dir + full_name + "-boundary" + gis_file_ext

    area = None

    if os.path.exists(path):
        area = gpd.read_file(path)
        nb_skipped += 1
    else:
        try:
            area = function(name_or_id)
            
            logger.info("%s downloaded", name)

            area["downloaded"] = datetime.date.today().strftime(datetime_format)
            area["country"] = country
            area["name"] = name

            area.to_file(path)
            logger.info("%s's boundaries saved", name)
            nb_downloaded += 1

        except ValueError:
            logger.error("%s not found by Nominatim. Check the spelling.", name)
            nb_failed += 1

        except requests.exceptions.Timeout:
            logger.error("%s triggered a timeout.", name)
            nb_failed += 1

        except requests.exceptions.ConnectionError as conn_error:
            logger.error("Failed due to a connection error after 10 attempts.\n%s",conn_error )
            nb_failed += 1

    return area, nb_skipped, nb_downloaded, nb_failed


def download_boundaries(country, names):
    logger.info("%s : Downloading boundaries, number of names: %s.", country.upper(), len(names))
    #print(f"Downloading boundaries in {country}, number of names: {len(names)}.")

    country_ascii = diacritics_to_ascii(country)
    create_dir_if_needed(nominatim_dir + country_ascii)

    nb_downloaded = 0
    nb_skipped = 0
    nb_failed = 0

    areas = None  # this will be a geodataframe, but it seemed easier to initialise with None than to specify all columns

    for name in names:
        params = {
            "country_ascii": country_ascii,
            "nb_downloaded": nb_downloaded,
            "nb_skipped": nb_skipped,
            "nb_failed": nb_failed,
            "country": country,
        }
        if isinstance(name, list):
            params["id"] = name[1]
            area, nb_skipped, nb_downloaded, nb_failed = get_boudaries_id_names(
                getting_boundary_from_id, name=name[0], **params
            )
        else:
            area, nb_skipped, nb_downloaded, nb_failed = get_boudaries_id_names(
                getting_boundary_from_osmnx, name=name, **params
            )
        if area is None:
            continue
        elif areas is None:
            areas = area
        else:
            areas = areas.append(area)
    logger.info("Areas downloaded: %s, skipped: %s, failed: %s/%s}.",nb_downloaded,nb_skipped,nb_failed, len(names)  )
    save_boundaries(areas, country_ascii)

    return areas


def save_boundaries(areas, label, verbose=False):

    areas = calc_area_info(areas) 

    # Save a single geojson with all boundaries
    path = nominatim_dir + label + "-boundaries" + gis_file_ext
    areas.to_file(path)
    if verbose:
        logger.info("Saved %s", path)

    # Save a CSV with coordinates of central points of all areas
    # Might be useful for simple maps
    coords = areas[["country", "name", "area", "lat", "lon"]]
    path = nominatim_dir + label + "-coordinates.csv"
    coords.to_csv(path, index=False)
    if verbose:
        logger.info("Saved %s", path)
