# Maps

This directory contains maps and scripts for manipulating them. Generally this was only needed for the start of the project and for redistricting. 

## Redistricting Process

1. `overlap_between_maps`: Calculate how much of each old district is in each new district. 
2. `assign_map_colors`: For the new map, assign the color from the old district that most overlaps with the new district to the new district. 
    3. Districts change numbers but have substantial overlap, so I want the colors to follow the overlap.
3. `find_neighbors_20221`: Determine the neighbors for each district and make sure that neighbors don't have the same color. 
4. `find_points_for_labels.py`: Run this script to create the lat/lon points that in the center of each SMD. The labels on the web map will be placed at these points. 
5. Upload these items to Mapbox Tilesets:
    6. SMD shapes, as GeoJSON
    7. Lat/lon points for labels, as CSV
    8. ANC shapes
9. Make changes in the Mapbox Studio to point at these new tilesets.



If more than 50% of a 2012 district by area is now represented by a 2022 district, the 2022 district should have the 2012 district's color.

If it's less than 50%, pick a new color at random that doesn't conflict with the neighbors (that matches the neighborhood character)