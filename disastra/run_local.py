import sys, os
from importlib.machinery import FileFinder, SourceFileLoader

class SqlAlchemyCythonFilterFinder:
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith('sqlalchemy.') and fullname.endswith('_cy'):
            if path:
                mod_name = fullname.split('.')[-1]
                for p in path:
                    py_file = os.path.join(p, mod_name + '.py')
                    if os.path.isfile(py_file):
                        from importlib.util import spec_from_file_location
                        return spec_from_file_location(fullname, py_file)
        return None

sys.meta_path.insert(0, SqlAlchemyCythonFilterFinder())

import uvicorn

if __name__ == "__main__":
    print("\n" + "="*50)
    print(">>> Disastra server starting on http://localhost:8000")
    print(">>> Open frontend in browser: http://localhost:8000")
    print(">>> Swagger API docs: http://localhost:8000/docs")
    print("="*50 + "\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
