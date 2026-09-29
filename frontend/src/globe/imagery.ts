import {
  ArcGisMapServerImageryProvider,
  ImageryLayer,
  TileMapServiceImageryProvider,
  buildModuleUrl,
  type Viewer,
} from "cesium";

// Esri World Imagery: real satellite tiles, no API key. Cesium shows the required attribution.
const ESRI = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";

/**
 * Natural Earth II ships with Cesium, so the planet paints instantly and works offline.
 * Esri satellite imagery goes on top; at globe scale it reads as a proper blue and green Earth, and it
 * carries on down to individual buildings on the campus map.
 */
export function addEarthImagery(viewer: Viewer) {
  viewer.imageryLayers.add(ImageryLayer.fromProviderAsync(TileMapServiceImageryProvider.fromUrl(buildModuleUrl("Assets/Textures/NaturalEarthII"))));
  viewer.imageryLayers.add(ImageryLayer.fromProviderAsync(ArcGisMapServerImageryProvider.fromUrl(ESRI, { enablePickFeatures: false })));
}
