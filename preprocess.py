import pandas as pd
pd.options.mode.chained_assignment = None  

import numpy as np
from geojson_length import calculate_distance, Unit
from geojson import Feature, LineString, MultiLineString
import geopandas as gpd
from datetime import datetime
import time
import os
import glob

#calls functions in the other scripts
from .config import *
from data.urban_nodes import *
from .utils import scaled_length, create_dir_if_needed, load_gdf_if_exists, diacritics_to_ascii, calc_area_info
from .osmnx import getting_data_from_osmnx #calls the designed function
from .boundaries import download_boundaries

import logging
logger= logging.getLogger(__name__)

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

### Combines bycicle tags. 
def oneway_status(oneway, oneway_bicycle):
    """combines oneway and oneway:bicycle tags into single status, ignoring irrelevant values
    returns:
    'twoway' if the street is bidirectional both for cars and bicycles
    'contra' if the street is unidirectional for cars with contraflow cycling allowed
    'oneway' if the street is unidirectional both for cars and bicycles"""

    if oneway != "yes":
        return "twoway"

    if oneway_bicycle == "no":
        return "contra"

    return "oneway"

### Defines the cycleway type. SImplifies the lines.
def get_cycleway_type(s):
  if (s == 'track') | (s == 'opposite_track'):
    return 'track'
  if (s == 'lane') | (s == 'opposite_lane'):
    return 'lane'
  if (s == 'share_busway') | (s == 'opposite_share_busway'):
    return 'busway'
  return None

### 
def cycle_infrastructure(row, infra_type, prefix = None):
  if prefix is None: # standalone infrastructure, oneway attribute can be used directly
    bidirectional = (row.get('oneway')!='yes') & (row.get('oneway:bicycle')!='yes')  
  else: # part of the highway, oneway by default, need to be explicitely tagged otherwise if not
    bidirectional = (row.get(prefix + 'oneway') == 'no')
  return { 'infra_type': infra_type,
           'bidirectional': bidirectional,
           'surface': row.get('surface' if prefix is None else prefix + 'surface'),
           'smoothness': row.get('smoothness' if prefix is None else prefix + 'smoothness'),
           'length_km': row['length_km'],
           'geometry': row['geometry'] }

### 
def extract_cycle_infra_from_highway (res, row):
  # the code examines a single 'highway' type feature and returns 0, 1 or 2 new entries to the table with cycling infrastructure

  # cycle track
  if (row['highway'] == 'cycleway'):
    res.append(cycle_infrastructure(row, 'track'))
    return res

  # separate cycle and pedestrian track
  if ((row['highway'] == 'path') | (row['highway'] == 'footway')) & (row.get('bicycle') == 'designated'):
    res.append(cycle_infrastructure(row, 'shared_pedestrians'))
    return res

  # pedestrian track with cycling allowed
  if ((row['highway'] == 'path') | (row['highway'] == 'footway')) & (row.get('bicycle') == 'yes'):
    res.append(cycle_infrastructure(row, 'pedestrian'))
    return res

  # cycle street
  if (row.get('cyclestreet') == 'yes') | (row.get('bicycle_road') == 'yes'):
    res.append(cycle_infrastructure(row, 'street'))
    return res

  # cycle tracks or lanes on both sides of the road
  infra = get_cycleway_type(row.get('cycleway:both')); 
  if(infra):
    r = cycle_infrastructure(row, infra, 'cycleway:both:')
    res.append(r)
    res.append(r)
    return res

  # cycle tracks or lanes without specified location
  infra = get_cycleway_type(row.get('cycleway'))
  if(infra):
    r = cycle_infrastructure(row, infra, 'cycleway:')
    res.append(r)
    if row.get('oneway') != 'yes':
      res.append(r)
    return res
    
  # cycle tracks or lanes on left and/or right side
  # we assume that cycleway:left & :right shouldn't be combined with cycleway or cycleway:both
  infra = get_cycleway_type(row.get('cycleway:left'))
  if(infra):
    res.append(cycle_infrastructure(row, infra, 'cycleway:left:'))
    
  infra = get_cycleway_type(row.get('cycleway:right'))
  if(infra):
    res.append(cycle_infrastructure(row, infra, 'cycleway:right:'))

  return res

def load_or_extract_cycle_infra (hdf, path_gis):
  """
  Extract cycle infrastructure from a GeoDaframe.

  params:
    hdf : GeoDataframe with all highways or all elements of the original pbf
    path_gis : where to save the resulting cycle network
  return:
    rdf : Another GeoDataframe with the 'infra_type', 'bidirectional','surface','smoothness','length_km' and 'geometry'.
  """
  
  rdf = load_gdf_if_exists(path_gis)
  if rdf is not None:
    return rdf

  # cycle network file not found, need to extract it from the highway network
  start_time = time.time()
  res = []
  for i, row in hdf.iterrows():
    res = extract_cycle_infra_from_highway(res, row) 

  if(len(res) == 0): # no cycle infra found
    rdf = gpd.GeoDataFrame()
  else: # there is cycle infra
    rdf = gpd.GeoDataFrame(res, geometry='geometry')
    rdf['scaled_length_km'] = rdf.apply(scaled_length, axis=1)
    rdf.to_file(path_gis, index=False, crs=gis_crs)
  # endif

  logger.info(f'Extracted {len(res)} cycle infrastructure elements in {time.time() - start_time:.3f} s.')
  return rdf

def process_highway_network(area, gdf, path_gis, path_csv):
  """
  Processes a single network (e.g.: city, district, region). Takes a highway network, extracts the cycle (sub)network, and create a summary. 
  Saves the extracted cycle network and summary line in dedicated files. 
  Parameters:
    area     - metadata and geometry 
    gdf      - geodataframe with all OSM highways in the area
    path_gis - where to save the resulting cycle network
    path_csv - where to save the summary csv
  Returns:
    summary line to include in country and general summaries
  """
  
  start_time = time.time()
  # one way and contraflow statistics for local streets
  local_streets = gdf.loc[gdf['highway'].isin(local_roads_cat), :] 
  local_streets['direction'] = local_streets.apply(
    lambda row: oneway_status(
      row.get('oneway'), row.get('oneway:bicycle')
      ), axis=1)
  local_oneway_km = local_streets.loc[(local_streets['direction'] == 'oneway'), 'length_km'].sum() 
  local_twoway_km = local_streets.loc[(local_streets['direction'] == 'twoway'), 'length_km'].sum() 
  local_contra_km = local_streets.loc[(local_streets['direction'] == 'contra'), 'length_km'].sum() 
  if local_contra_km > 0: # to avoid dividing by 0
    ratio_contraflow = local_contra_km / (local_contra_km + local_oneway_km)
  else:
    ratio_contraflow = 0
  logger.info("Processed local streets in %.3f s.", time.time() - start_time)

  # load or extract cycle network
  network = load_or_extract_cycle_infra(gdf, path_gis)

  start_time = time.time()
  date = datetime.today().strftime(datetime_format)

  # general stats 
  main_roadnetwork_km  = gdf.loc[gdf['highway'].isin(main_roads_cat)  , 'length_km'].sum()
  local_roadnetwork_km = gdf.loc[gdf['highway'].isin(local_roads_cat) , 'length_km'].sum()

  arnaud_summary = dict()
  # metadata  
  arnaud_summary['Country'] = area['country']
  arnaud_summary['City'] = area['name']
  arnaud_summary['Lat, Lon'] = area['lat'].astype(str) + ', ' + area['lon'].astype(str)
  arnaud_summary['Area'] = area['area']
  arnaud_summary['Date'] = datetime.today().strftime(datetime_format)

  arnaud_summary['overview-main-road-network']  = [main_roadnetwork_km]
  arnaud_summary['overview-local-road-network'] = [local_roadnetwork_km]
   
  # FIXME: reorganise the code to make the order more logica
  # or number the fields and sort the columns before saving?
  arnaud_summary['local-contra'] = [local_contra_km]
  arnaud_summary['local-oneway'] = [local_oneway_km]
  arnaud_summary['local-twoway'] = [local_twoway_km]
  arnaud_summary['ratio-contraflow'] = [ratio_contraflow]

  if not network.empty:
    network['scaled_length_km'] = network.apply(scaled_length, axis=1)
    network.to_file(path_gis, index=False, crs=gis_crs)

    #SCALED LENGTH simplified [AB]
    tracks_scaled_sum = (network.loc[(network['infra_type'] == 'track'), 'scaled_length_km'].sum())
    lanes_scaled_sum  = (network.loc[(network['infra_type'] == 'lane'), 'scaled_length_km'].sum())
    shared_scaled_sum = (network.loc[(network['infra_type'] == 'shared_pedestrians'), 'scaled_length_km'].sum())
    total_scaled_sum = tracks_scaled_sum + lanes_scaled_sum + shared_scaled_sum
    
    busways_scaled_sum = (network.loc[(network['infra_type'] == 'busway'), 'scaled_length_km'].sum())
    streets_scaled_sum = (network.loc[(network['infra_type'] == 'street'), 'scaled_length_km'].sum())
    extended_scaled_sum = total_scaled_sum + busways_scaled_sum + streets_scaled_sum

    ratio_tracks_scaled = (tracks_scaled_sum / main_roadnetwork_km)
    ratio_totalinfra_scaled = (total_scaled_sum / main_roadnetwork_km)

    arnaud_summary['overview-cycle_tracks-km'] = [tracks_scaled_sum]
    arnaud_summary['overview-cycle_lanes-km'] = [lanes_scaled_sum]
    arnaud_summary['overview-shared_pedestrians-km'] = [shared_scaled_sum]
    arnaud_summary['overview-total-cycle-infrastructure'] = [total_scaled_sum]
    arnaud_summary['overview-busways-km'] = [busways_scaled_sum]
    arnaud_summary['overview-cycle_streets-km'] = [streets_scaled_sum]
    arnaud_summary['overview-ext-cycle-infrastructure'] = [extended_scaled_sum]

    arnaud_summary['ratio-cycle_tracks-main_roads'] = [ratio_tracks_scaled]
    arnaud_summary['ratio-cycle_infra-main_roads'] = [ratio_totalinfra_scaled]
    arnaud_summary=pd.DataFrame.from_dict(arnaud_summary)

    sum_infra = network.groupby(['infra_type','bidirectional'])['scaled_length_km'].sum() 
    flat_sum_infra = sum_infra.reset_index()
    flat_sum_infra['bidirectional'] = flat_sum_infra['bidirectional'].astype(str).replace({'True':'bidirectional', 'False':'unidirectional','1.0':'bidirectional', '0.0':'unidirectional' })
    flat_sum_infra['combined'] = 'type-' + flat_sum_infra['infra_type']  + '-' + flat_sum_infra['bidirectional']
    flat_sum_infra.drop(['infra_type', 'bidirectional'], axis=1, inplace=True)
    flat_sum_infra.set_index('combined',inplace=True)
    transposed_sum_infra = flat_sum_infra.transpose().reset_index(drop=True)

      # FIXME: probably we could filter out invalid surface types to not produce thousand columns (e.g. have a common column track-surface-invalid)?

    surface_network = network.loc[
      network['infra_type'].isin(infra_types_for_surface_stats)
      ].fillna('unknown') # produce surface stats only for selected infrastructure types, add an extra column for unknown
    sum_surface = surface_network.groupby(['infra_type','surface'], dropna=False)['scaled_length_km'].sum()
    flat_sum_surface = sum_surface.reset_index()
    flat_sum_surface['combined'] = 'surface-' + flat_sum_surface['infra_type'].astype(str) + '-' + flat_sum_surface['surface']
    flat_sum_surface.drop(['infra_type', 'surface'], axis=1, inplace=True)
    flat_sum_surface.set_index('combined',inplace=True)
    transposed_sum_surface = flat_sum_surface.transpose().reset_index(drop=True)

    final_for_this_city = pd.concat([arnaud_summary, transposed_sum_infra, transposed_sum_surface], axis=1)
    #final_for_this_city['surface-track-nodata'] = (network.loc[(network['surface'].isnull()) & (network['infra_type'] == 'track'), 'scaled_length_km'].sum()) 
  else:
    final_for_this_city = pd.DataFrame.from_dict(arnaud_summary)

  final_for_this_city.to_csv(path_csv, index=False,  float_format='%.3f')

  logger.info("Generated summary in %.3f s.", time.time() - start_time)
  return final_for_this_city # we return the summary line to include in country and general summaries

# download and process single highway network

def download_highway_network(area, target_dir):
  """
  Download a single highway network (e.g.: city, district, region) and pass it over to process_highway_network()
  Parameters:
    area       - metadata and geometry 
    target_dir - where to save the results
  Returns:
    'skipped'  - if the area has been processed already
    'empty'    - if no highway network found in the area
    'OK'       - if processed
  """

  country_ascii = diacritics_to_ascii(area['country'])
  name_ascii = diacritics_to_ascii(area['name'])
  create_dir_if_needed(target_dir + country_ascii)
  prefix = target_dir + country_ascii + '/' + name_ascii
  
  path_hws = prefix + '-highway_network' + gis_file_ext  
  path_gis = prefix + '-cycle_network' + gis_file_ext
  path_csv = prefix + '-summary.csv'

  if os.path.exists(path_csv):
    logger.info("   %s has been processed already", area['name'])
    return "skipped"

  start_time = time.time()
  if os.path.exists(path_hws): # Highway network downloaded, not processed
    logger.info("   %s has been downloaded already, reading from file", area['name'])
    gdf = gpd.read_file(path_hws, encoding='utf-8')
    logger.info("Loaded %s highways in %.3f s.", gdf.shape[0], time.time() - start_time)

  else: # Highway network needs downloading
    logger.info("Downloading highways for %s", area['name'])
    gdf = getting_data_from_osmnx(area['geometry'])
    n_highways = gdf.shape[0]
    gdf = gdf.loc[gdf.geometry.geometry.type=='LineString']
    n_linestr  = gdf.shape[0]
    logger.info("Downloaded %s highways (%s linestrings) in %.3f s.", n_highways, n_linestr, time.time() - start_time)
    if n_linestr == 0:
      return 'empty'

    start_time = time.time()
    gdf = gdf.clip(area['geometry'], keep_geom_type=True)
    available_columns_to_keep = set(highway_columns_to_keep).intersection(set(gdf.columns))
    gdf = gdf[available_columns_to_keep]
    gdf['length_km'] = gdf.apply(lambda row: calculate_distance(Feature(geometry=row["geometry"]), Unit.kilometers), axis=1)
    logger.info("Clipped and measured highway network in %.3f s.", time.time() - start_time)

    start_time = time.time()
    gdf.to_file(path_hws, index=False, crs=gis_crs)
    logger.info("Saved highway network in %.3f s.", time.time() - start_time)

  # the following line works, but takes a lot of time; tbd whether to use it
  # gdf.to_file(path_hws)
  # with open(path_hws, "w") as f:
  #  f.write(gdf.to_json()) 
  # You can then load it like this:
  #  with open(path_gis, "r") as f:
  #   features = json.load(f)
  #   gdf2 = gpd.GeoDataFrame.from_features(features)
  ## https://pyogrio.readthedocs.io/en/latest/introduction.html#write-a-geopandas-geodataframe
  
  process_highway_network(area, gdf, path_gis, path_csv)
  return 'OK'

def load_boundaries(boundaries_file, nuts = False):
  """
  Parameters:
    boundaries_file - GIS file with polygons delimiting areas
    nuts - NUTS file, columns need to be renamed to include country and name 
  """

  if not os.path.exists(boundaries_file):
    logger.info(f'File {boundaries_file} not found.')
    return None

  # Probably it would be good to add 'try:' 'except:' here?
  areas = gpd.read_file(boundaries_file)
  logger.info(f'{areas.shape[0]} areas read from {boundaries_file}')

  if nuts:
    areas = areas.rename(columns = nuts_column_names)

    # FIXME: 
    # - add some fallback options in case the boundary file doesn't have name and country columns?
    # - and/or make it more configurable
    # - include additional info?
  return areas

def download_highway_networks(areas, target_dir):
  """
  Download and process highway networks for all areas listed.
  Parameters:
    boundaries_file - GIS file with polygons delimiting areas
    target_dir      - where to save the results
  Returns:
    number of processed areas
  """
  create_dir_if_needed(target_dir)

  nb_processed = 0
  nb_empty = 0
  nb_skipped = 0
  nb_failed = 0
 
  for i in range(0, len(areas)):  
    # colab python doesn't seem to understand match and case
    res = download_highway_network(areas.iloc[i], target_dir)
    if res == 'OK':
      nb_processed += 1
    elif res == 'empty':
      nb_empty += 1
    elif res == 'skipped':
      nb_skipped +=1
    else:
      nb_failed += 1
       
  # end of the main for loop 
  # (I hate depending on indents for code structure)
  
  logger.info(f'Highway networks processed: {nb_processed}, empty: {nb_empty}, skipped: {nb_skipped}, failed: {nb_failed} / {areas.shape[0]}.') 
  return nb_processed

def merge_summary_csv(folder, subfolder):
    # merge all summary CSV from folder/subfolder and save the result in parent folder

    list_files = glob.glob(folder + subfolder + "/*summary.csv")
    logger.info("Merging %d CSV files in %s.", len(list_files), folder + subfolder)
    summary = pd.concat(map(pd.read_csv, list_files), ignore_index=True)
    summary = summary.sort_values(['Country', 'City'], ascending=[True, True])
    summary.to_csv(folder + subfolder + "-summary.csv", index=False)

def process_country(country):
    # process all urban nodes from one country
    country_ascii = diacritics_to_ascii(country)
    download_boundaries(country, urban_nodes[country])
    areas = load_boundaries(nominatim_dir + country_ascii + "-boundaries" + gis_file_ext)
    download_highway_networks(areas, cyclenetworks_dir)
    merge_summary_csv(cyclenetworks_dir, country_ascii)


def process_all():
    # Should check all cities on the urban node list of lists,
    # If there's no boundary/network download and process necessary info
    # Create 1 summary / country and 1 general in the main output folder

    for country in urban_nodes.keys():
        process_country(country)
    merge_summary_csv(output_dir, "cyclenetworks")

def process_nuts():
  for country in nuts_country_codes:
    areas = load_boundaries(nuts_dir + country + gis_file_ext, nuts = True)
    areas = calc_area_info(areas, point = True)
    download_highway_networks(areas, cyclenetworks_dir)
    merge_summary_csv(cyclenetworks_dir, country)