# rebuild & reset DB
docker compose build scraper

docker compose down -v

docker compose up -d db db-init kafka zookeeper


docker compose run --rm \
  -e DB_URL=postgresql+psycopg://tiktok:tiktok@db:5432/tiktok \
  scraper \
  
  python -m scripts.init_db

# 2. now seed
docker compose run --rm \
  -e DB_URL=postgresql+psycopg://tiktok:tiktok@db:5432/tiktok \
  scraper \
  
python -m scripts.seed_product 1731176959119036424




# start scraper
docker compose up -d scraper

docker compose logs -f scraper

Example:	Labubu product id: 1731176959119036424

Popmart seller seed: 7495316114727995400
