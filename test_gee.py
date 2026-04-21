import ee
ee.Initialize(project='ee-stephaniegeorge')

# JRC GFC2020 V3 (versión actualizada)
try:
    jrc1 = ee.ImageCollection('JRC/GFC2020/V3').first().bandNames().getInfo()
    print('JRC GFC2020 V3 bands:', jrc1)
except Exception as e:
    print('JRC GFC2020 V3 error:', e)

# JRC Global Surface Water
try:
    jrc2 = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').bandNames().getInfo()
    print('JRC GSW bands:', jrc2)
except Exception as e:
    print('JRC GSW error:', e)

# PRODES deforestacion Brazil
try:
    prodes = ee.ImageCollection('projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1').first().bandNames().getInfo()
    print('MapBiomas bands:', prodes)
except Exception as e:
    print('MapBiomas error:', e)

# JRC TMF con path alternativo
try:
    tmf = ee.ImageCollection('projects/JRC/TMF/v1_2023/AnnualChanges').first().bandNames().getInfo()
    print('JRC TMF alt bands:', tmf)
except Exception as e:
    print('JRC TMF alt error:', e)