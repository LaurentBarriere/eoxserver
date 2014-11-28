define(["backbone","communicator","globals","openlayers","models/MapModel","filesaver"],function(a,b,c){var d=a.View.extend({onShow:function(){var a=new ol.control.MousePosition({coordinateFormat:ol.coordinate.createStringXY(4),projection:"EPSG:4326",undefinedHTML:"&nbsp;"});this.geojson_format=new ol.format.GeoJSON,this.map=new ol.Map({controls:ol.control.defaults().extend([a]),renderer:"canvas",target:"map",view:new ol.View({center:[9,45],zoom:6,projection:ol.proj.get("EPSG:4326")})}),console.log("Created Map");var d=this;this.map.on("moveend",function(a){var c=a.map.getView(),e=c.getCenter();b.mediator.trigger("router:setUrl",{x:e[0],y:e[1],l:c.getZoom()}),b.mediator.trigger("map:position:change",d.onGetMapExtent())}),this.listenTo(b.mediator,"map:center",this.centerMap),this.listenTo(b.mediator,"map:layer:change",this.changeLayer),this.listenTo(b.mediator,"map:set:extent",this.onSetExtent),this.listenTo(b.mediator,"productCollection:sortUpdated",this.onSortProducts),this.listenTo(b.mediator,"productCollection:updateOpacity",this.onUpdateOpacity),this.listenTo(b.mediator,"selection:activated",this.onSelectionActivated),this.listenTo(b.mediator,"map:load:geojson",this.onLoadGeoJSON),this.listenTo(b.mediator,"map:export:geojson",this.onExportGeoJSON),this.listenTo(b.mediator,"time:change",this.onTimeChange),b.reqres.setHandler("map:get:extent",_.bind(this.onGetMapExtent,this)),b.reqres.setHandler("get:selection:json",_.bind(this.onGetGeoJSON,this));var e=new ol.style.Style({fill:new ol.style.Fill({color:"rgba(255, 255, 255, 0.2)"}),stroke:new ol.style.Stroke({color:"#ffcc33",width:2}),image:new ol.style.Circle({radius:7,fill:new ol.style.Fill({color:"#ffcc33"})})});return this.source=new ol.source.Vector,this.source.on("change",this.onDone),this.vector=new ol.layer.Vector({source:this.source,style:e}),this.boxstart=void 0,this.drawControls={pointSelection:new ol.interaction.Draw({source:this.source,type:"Point"}),lineSelection:new ol.interaction.Draw({source:this.source,type:"LineString"}),polygonSelection:new ol.interaction.Draw({source:this.source,type:"Polygon"}),bboxSelection:new ol.interaction.DragBox({style:e})},this.drawControls.bboxSelection.on("boxstart",function(a){this.boxstart=a.coordinate},this),this.drawControls.bboxSelection.on("boxend",function(a){var b=a.coordinate,c=new ol.geom.Polygon([[[this.boxstart[0],this.boxstart[1]],[this.boxstart[0],b[1]],[b[0],b[1]],[b[0],this.boxstart[1]]]]),d=new ol.Feature;d.setGeometry(c),this.source.addFeature(d)},this),this.baseLayerGroup=new ol.layer.Group({layers:c.baseLayers.map(function(a){return this.createLayer(a)},this)}),this.map.addLayer(this.baseLayerGroup),this.productLayerGroup=new ol.layer.Group({layers:c.products.map(function(a){return this.createLayer(a)},this)}),this.map.addLayer(this.productLayerGroup),c.products.each(function(a){if(a.get("visible")){var c={id:a.get("view").id,isBaseLayer:!1,visible:!0};b.mediator.trigger("map:layer:change",c)}}),this.overlayLayerGroup=new ol.layer.Group({layers:c.overlays.map(function(a){return this.createLayer(a)},this)}),this.map.addLayer(this.overlayLayerGroup),this.onSortProducts(),this.map.addLayer(this.vector),$(".ol-attribution").attr("class","ol-attribution"),this},createLayer:function(a){for(var b=null,c=a.get("view"),d=ol.proj.get("EPSG:4326"),e=d.getExtent(),f=ol.extent.getWidth(e)/256,g=new Array(18),h=new Array(18),i=0;18>i;++i)g[i]=f/Math.pow(2,i+1),h[i]=i;switch(c.protocol){case"WMTS":b=new ol.layer.Tile({visible:a.get("visible"),source:new ol.source.WMTS({urls:c.urls,layer:c.id,matrixSet:c.matrixSet,format:c.format,projection:c.projection,tileGrid:new ol.tilegrid.WMTS({origin:ol.extent.getTopLeft(e),resolutions:g,matrixIds:h}),style:c.style,attributions:[new ol.Attribution({html:c.attribution})]})});break;case"WMS":b=new ol.layer.Tile({visible:a.get("visible"),source:new ol.source.TileWMS({crossOrigin:"anonymous",params:{LAYERS:c.id,VERSION:"1.1.0",FORMAT:"image/png"},url:c.urls[0]}),attribution:c.attribution})}return b&&(b.id=c.id),b},centerMap:function(a){console.log(a),this.map.getView().setCenter([parseFloat(a.x),parseFloat(a.y)]),this.map.getView().setZoom(parseInt(a.l))},changeLayer:function(a){if(a.isBaseLayer)c.baseLayers.forEach(function(b){b.get("view").id==a.id?b.set("visible",!0):b.set("visible",!1)}),this.baseLayerGroup.getLayers().forEach(function(b){b.setVisible(b.id==a.id?!0:!1)});else{var b=c.products.find(function(b){return b.get("view").id==a.id});b?(b.set("visible",a.visible),this.productLayerGroup.getLayers().forEach(function(b){b.id==a.id&&b.setVisible(a.visible)})):(c.overlays.find(function(b){return b.get("view").id==a.id}).set("visible",a.visible),this.overlayLayerGroup.getLayers().forEach(function(b){b.id==a.id&&b.setVisible(a.visible)}))}},onSortProducts:function(){var a=this.productLayerGroup.getLayers(),b={};c.products.each(function(a,d){b[a.get("view").id]=c.products.length-(d+1)});var d=_.sortBy(a.getArray(),function(a){return b[a.id]});this.productLayerGroup.setLayers(new ol.Collection(d)),console.log("Map products sorted")},onUpdateOpacity:function(a){var b=a.model.get("view").id;this.productLayerGroup.getLayers().forEach(function(c){c.id==b&&c.setOpacity(a.value)})},onSelectionActivated:function(a){if(a.active)for(key in this.drawControls){var c=this.drawControls[key];if(a.id==key)this.map.addInteraction(c);else{this.map.removeInteraction(c);var d=this.source.getFeatures();for(var e in d)this.source.removeFeature(d[e]);b.mediator.trigger("selection:changed",null)}}else for(key in this.drawControls){var c=this.drawControls[key];this.map.removeInteraction(c);var d=this.source.getFeatures();for(var e in d)this.source.removeFeature(d[e]);b.mediator.trigger("selection:changed",null)}},onLoadGeoJSON:function(a){var b=this.source.getFeatures();for(var c in b)this.source.removeFeature(b[c]);var d,e=new ol.source.GeoJSON({object:a}),f=e.getFeatures();if(f){f.constructor!=Array&&(f=[f]);for(var c=0;c<f.length;++c)d?d.extend(f[c].getGeometry().getExtent()):d=f[c].getGeometry().getExtent();this.source.addFeatures(f),this.map.getView().fitExtent(d,this.map.getSize())}},onExportGeoJSON:function(){var a,b=this.vector.getSource().getFeatures(),c=JSON.stringify(this.geojson_format.writeFeatures(b)),a=new Blob([c],{type:"text/plain;charset=utf-8"});saveAs(a,"selection.geojson")},onGetGeoJSON:function(){var a=this.vector.getSource().getFeatures(),b=this.geojson_format.writeFeatures(a);return b},onGetMapExtent:function(){var a=this.map.getView().calculateExtent(this.map.getSize()),b={left:a[0],bottom:a[1],right:a[2],top:a[3]};return b},onSetExtent:function(a){this.map.getView().fitExtent(a,this.map.getSize())},onDone:function(a){var c=a.target.getFeatures().pop(),d=null;c&&(d=c.getGeometry()),b.mediator.trigger("selection:changed",d)},onTimeChange:function(a){var b=getISODateTimeString(a.start)+"/"+getISODateTimeString(a.end);c.products.each(function(a){if(a.get("timeSlider")){var c=a.get("view").id;this.productLayerGroup.getLayers().forEach(function(d){d.id==c&&("WMS"==a.get("view").protocol?d.getSource().updateParams({TIME:b}):"WMTS"==a.get("view").protocol&&d.getSource().updateDimensions({TIME:b}))})}},this)}});return{MapView:d}});