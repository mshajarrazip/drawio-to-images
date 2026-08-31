# drawio-to-images

A uvx tool that takes in .drawio file and spits out the image in any image format. 

User can pass a directory folder containing .drawio images or a path to .drawio images, and the tool will write to dst in any image formar (default is svg).

The tool keeps track of whether a .drawio file has any recent changes, and only re-generate new image when necessary. 

By default saves output to ./imgs ( where the tool is invoked ), and saves the hash of source to the appropriate folder ( suggest an appropriate location ) for keeping track of changes. 

All of this are configurable, of course. 