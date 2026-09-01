import typer

app = typer.Typer(help="Pocket Agent CLI")


@app.command()
def hello() -> None:
    print("Hello Pocket Agent!")


def main() -> None:
    app()


if __name__ == "__main__":
    main()