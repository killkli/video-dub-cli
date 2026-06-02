#!/usr/bin/env python3
import sys
print('Python:', sys.version)
try:
    import pydantic
    print('Pydantic:', pydantic.__version__)
except ImportError as e:
    print('pydantic not installed:', e)
try:
    import yaml
    print('PyYAML:', yaml.__version__)
except ImportError as e:
    print('yaml not installed:', e)
try:
    import pytest
    print('pytest:', pytest.__version__)
except ImportError as e:
    print('pytest not installed:', e)