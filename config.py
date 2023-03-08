# Placeholder for general configuration, e.g. timeout, output formats etc.
# Eventually should be moved somewhere to the front

# Where do the files go, directory structure
# Paths should end with /
import pathlib
import os

file_path = pathlib.Path.cwd()
output_dir = os.path.join(file_path, "outputs\\")  # root
nominatim_dir = output_dir + "nominatim\\"
cyclenetworks_dir = output_dir + "cyclenetworks\\"

# .gpkg seems to be better and more compact than .geojson or shapefiles
# some arguments: https://samashti.tech/why-you-need-to-use-geopackage-files-instead-of-shapefile-or-geojson/
gis_file_ext = ".gpkg"
gis_crs = 'EPSG:4326'

datetime_format = "%Y-%m-%d %H:%M"

# Categories of roads to download and process
main_roads_cat = [
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
]

local_roads_cat = [
    "residential", 
    "living_street"
] 

active_roads_cat = [
    "cycleway",
    "footway",
    "path",
    "pedestrian",
    "track",
    'service' # FIXME: to sort it out later
]  

roads_cat = main_roads_cat + local_roads_cat + active_roads_cat #the geometries that are extracted  later

# Attributes of highways we might need
# We'll need to add more if we want to assess stress level
highway_columns_to_keep  = [
    'highway', 'bicycle', 
    'cycleway', 'cycleway:right','cycleway:left', 'cycleway:both', 
    'oneway', 'oneway:bicycle', 'surface', 'smoothness',
    'cycleway:oneway', 'cycleway:surface', 'cycleway:smoothness',
    'cycleway:left:oneway', 'cycleway:left:surface', 'cycleway:left:smoothness',
    'cycleway:right:oneway', 'cycleway:right:surface', 'cycleway:right:smoothness',
    'cycleway:both:oneway', 'cycleway:both:surface', 'cycleway:both:smoothness',
    'cyclestreet', 'bicycle_road',
    'access', 'vehicle',
    'length_km', 'geometry' 
]

# types of cycling infrastructure to include in the statistics for surface
infra_types_for_surface_stats = [
    'track', 'shared_pedestrians'
    ]

#revisar, no entiendo.
#Nomenclature des Unites territoriales statistiques - NUTS

nuts_dir = 'data/NUTS/nuts3_by_country/'

nuts_country_codes = ['BE', 'NL', 'LU']

nuts_column_names = {
    'CNTR_CODE' : 'country',
    'NAME_LATN': 'name'
}

