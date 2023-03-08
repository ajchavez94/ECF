from http.client import FOUND
import os
import unicodedata
import logging
import time
import geopandas as gpd

from .config import gis_file_ext, gis_crs

logger = logging.getLogger(__name__)

#Function that replaces diacritics to closest ASCII characterers. 
def diacritics_to_ascii(text):
    """
    Replaces diacritics with the closest ASCII characters,
    to make the names safe to use for example as filenames.
    """
    # first fix some characters not caught by unicode normalize
    # we might need to add more here later as we expand our name base,
    # this is just based on the list of urban nodes
    text = text.replace("Ł", "L").replace("ł", "l").replace("ß", "ss").replace(" ", "_").replace('/','_')

    # then use normalize to get rid of accents and other decomposables
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8")
    return str(text)


def create_dir_if_needed(path):
    """
    Creates a directory and all necessary parent folders if they do not exist already.
    """
    if not os.path.exists(path):
        os.makedirs(path)
        logger.info("Directory created: %s", path)


#create geodataframe if the path exists.
def load_gdf_if_exists(path):
  if not os.path.exists(path): # file not found
    return None
  
  start_time = time.time()
  logger.info("Loading %s", path)
  gdf = gpd.read_file(path, encoding='utf-8')
  logger.info("Loaded %s features in %.3f s.", gdf.shape[0], time.time() - start_time)
  return gdf

#scale lenght
def scaled_length(row):
    """
    Returns full length for bidirectional infrastructure and half length for unidirectional infrastructure.
    """
    # FIXME: why do we use 1.0 & 0.0 for sth that should be boolean?
    # Comment from Ele: I don't remember specifically, but I believe those were
    # the values produced in the table when downloading the highway network
    if row["bidirectional"] == 1.0:
        return row["length_km"]
    elif row["bidirectional"] == 0.0:
        return row["length_km"] / 2

######Calculate areas divided by 10**6 
def calc_area_info(areas, point = False):
  areas_copy = areas.copy().to_crs({"proj": "cea"}) #makes a copy of the areas and reprojected them into coordinates. 
  areas["area"] = areas_copy["geometry"].area / 10**6 # calculate the area in a given geometry and divides by 10**6, thus, transforming it. 

  if point:
    points = areas['geometry'].representative_point() #returns a geoseries of points that are inside the geometry. 
    areas['lon'] = points.geometry.apply(lambda p: p.x) #define coordinates
    areas['lat'] = points.geometry.apply(lambda p: p.y)

  return areas

#### Function that splits the geodataframe ### which is the utility

def split_gdf(input_file, target_dir, attribute):
  """
  Splits a GIS file into several basing on specific attribute
  """
  gdf = gpd.read_file(input_file)
  logger.info(f'{gdf.shape[0]} features read from {input_file}')#message to see how many features have been imported. 

  attr_values = gdf.loc[:, attribute].unique()#access a group of rows and columns by labels or a bollean arreau. Also selects elements without copies. 
  logger.info (f'Unique {attribute} values: {attr_values}') 

  create_dir_if_needed(target_dir)

  for i in attr_values:
    selection = gdf.loc[gdf[attribute] == i]
    path = target_dir + i + gis_file_ext
    selection.to_file(path) #save

### Function that merges gdf

def merge_gdf(input_dir, filter, output_path):
  files = os.listdir(input_dir)
  input_files = [f for f in files if filter in f] # For each f in the file, give me only the ones that match my included criteria.
  res = gpd.GeoDataFrame() #create a dtaframe
  for i in input_files: #for each i in the input file
    gdf = gpd.read_file(input_dir + i, crs=gis_crs) #creates a document reading the directory
    res = res.append(gdf)# add
    logger.info (f'{i} loaded.') 
  res.to_file(output_path,  crs=gis_crs)
  return res