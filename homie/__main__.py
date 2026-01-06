"""Allow homie to be executed as a module: python -m homie"""

from .cli import cli

if __name__ == "__main__":
    cli()

