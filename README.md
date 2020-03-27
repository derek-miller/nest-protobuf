# nest-protobuf
Project for extracting proto files from the Nest home website.

## Generate proto files from source:

1. Navigate to https://home.nest.com and login.
2. Once the UI has fully loaded, save the web page (If you are using chrome see [this](https://support.google.com/chrome/answer/7343019?co=GENIE.Platform%3DDesktop&hl=en) for instructions.)
3. Install python dependencies:
   1. `virtualenv .venv`
   2. `./bin/activate`
   3. `pip install -r requirements.txt`
4. Run program, passing in the path to the source downloaded in step 2.
   1. `python3 decompiler.py <page-files-folder>`
      1. This will cache the formatted js files in the `.cache/formatted-js-source` folder so subsequent runs will be much faster. You must delete this folder if you want to process newer source code.
5. This will output the generated proto files in a directory called `nest-protobuf-generated`.
6. From there you must manually assign the types for fields that use enums as it is not interpretable from the source. Look for `UNKNOWN_ENUM` in the generated files.


### TODO
* Generate the services proto file.
* Figure out how to determine the enum types for fields.
* Handle imports by looking at the source instead of a hardcoded type lookup.


## Create `descriptor-set` using [prototool](https://github.com/uber/prototool#prototool-descriptor-set)
This is very useful for debugging using the [Charles web debugging proxy](https://www.charlesproxy.com/):
```
cd nest-protobuf && prototool descriptor-set . --output-path nest-protobuf.desc --include-source-info --include-imports
```