"""Builds shop-lab: a Spring Boot 4 microservice shop with planted bugs, one commit per change, for testing Codist.

Two services: order-service (orders, stock, prices cached in Redis, money and date rules, and the nightly Spring
Batch settlement) and payment-service (charges, fraud limit, idempotency keys in Redis). Both use Spring MVC and JDBC
through JdbcClient (no JPA); order-service calls payment-service with OpenFeign.

The bugs come in three kinds:
  seen-rule   well-known Java mistakes that Codist's code checks look for
  seen-logic  classic logic mistakes common in public code, so likely in any model's training
  novel       mistakes that only show against this shop's own rules, written in its README, some of them across
              services (the Feign path), in Redis use or in the batch job
and two controls: a pure refactor (anything flagged there is a false alarm) and a fix of an earlier bug.

The answer key is written next to this script, never into the repository, so a model reviewing the repository
cannot read it. Commit messages describe the change the way a developer would, without naming the bug.

    python3 make_shop_lab.py ~/dev/shop-lab
"""
import json, os, subprocess, sys

DEST = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/dev/shop-lab"))
HERE = os.path.dirname(os.path.abspath(__file__))
BOOT, CLOUD = "4.0.6", "2025.1.2"
files = {}
truth = []


def git(*args):
    subprocess.run(["git", "-C", DEST, "-c", "user.name=Lab Dev", "-c", "user.email=dev@shop-lab.test",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def put(path, text):
    files[path] = text
    full = os.path.join(DEST, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def edit(path, old, new):
    text = files[path]
    assert text.count(old) == 1, (path, old)
    put(path, text.replace(old, new))


def line_of(path, needle):
    for i, l in enumerate(files[path].split("\n"), 1):
        if needle in l:
            return i
    raise SystemExit(f"{needle!r} not in {path}")


def commit(message, kind=None, bug=None, path=None, needle=None, rule=None, behaviour=False, service=None):
    git("add", "-A")
    git("commit", "-q", "-m", message)
    sha = subprocess.run(["git", "-C", DEST, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if kind:
        truth.append({"sha": sha, "message": message, "kind": kind, "bug": bug, "path": path,
                      "line": line_of(path, needle) if needle else None, "rule": rule,
                      "behaviourCanSee": behaviour, "service": service or path.split("/")[0]})


def pom(artifact, deps, packaging="jar", extra=""):
    dep_xml = "".join(f"""
    <dependency>
      <groupId>{g}</groupId>
      <artifactId>{a}</artifactId>
    </dependency>""" for g, a in deps)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.shoplab</groupId>
    <artifactId>shop-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
  </parent>
  <artifactId>{artifact}</artifactId>
  <packaging>{packaging}</packaging>
  <dependencies>{dep_xml}
  </dependencies>{extra}
</project>
"""


WEB = ("org.springframework.boot", "spring-boot-starter-web")
JDBC = ("org.springframework.boot", "spring-boot-starter-jdbc")
REDIS = ("org.springframework.boot", "spring-boot-starter-data-redis")
BATCH = ("org.springframework.boot", "spring-boot-starter-batch")
FEIGN = ("org.springframework.cloud", "spring-cloud-starter-openfeign")


def yml(name, port):
    return f"""spring:
  application:
    name: {name}
  data:
    redis:
      host: localhost
      port: 6379
server:
  port: {port}
"""


# ---------------------------------------------------------------- base: a correct shop

if os.path.exists(DEST):
    raise SystemExit(f"{DEST} exists; remove it first")
os.makedirs(DEST)
git("init", "-q", "-b", "main")

put("pom.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{BOOT}</version>
    <relativePath/>
  </parent>
  <groupId>com.shoplab</groupId>
  <artifactId>shop-lab</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <packaging>pom</packaging>
  <modules>
    <module>order-service</module>
    <module>payment-service</module>
  </modules>
  <properties>
    <java.version>21</java.version>
    <spring-cloud.version>{CLOUD}</spring-cloud.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-dependencies</artifactId>
        <version>${{spring-cloud.version}}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>
""")
put(".gitignore", "target/\n")

put("README.md", """# Shop Lab

A microservice shop for an Indian retailer, on Spring Boot 4.

| Service | Does | Talks to |
|---|---|---|
| order-service (8081) | orders, carts, stock, prices, nightly settlement (Spring Batch) | payment-service over Feign; Redis for cached prices; JDBC |
| payment-service (8082) | charges cards, fraud limits | Redis for idempotency keys; the card gateway |

All money is in paise (1 rupee = 100 paise) and held as `long`.

## Business rules

1. **One discount per order.** A coupon and a loyalty discount never stack: the customer gets whichever is larger.
2. **The business day is India time.** An order belongs to the calendar day in Asia/Kolkata; reports, settlement
   and daily limits all use this day.
3. **Bills split exactly.** When a bill is split between people, the parts must add up to the total; leftover
   paise go to the first people, one each.
4. **The fraud limit is inclusive.** A payment exactly at the customer's limit is allowed; only amounts above it
   are blocked.
5. **Cancelling releases what was reserved.** Stock reserved for an order may be less than the quantity ordered
   (back-orders); cancelling must give back only what was actually reserved.
6. **Prices are stored in rupees.** Converting to a foreign currency divides by the rate (rupees per unit of that
   currency); converting back multiplies.
7. **A payment is charged once.** A charge is identified by its idempotency key, kept in Redis for 24 hours; retries
   after a timeout must reuse the same key so the gateway does not charge twice.
8. **Pages are numbered from 1.** Page 1 is the first page of results.
9. **Settlement is all or nothing.** If any order of the day cannot be settled, the nightly run fails and is retried;
   it never quietly skips orders.
10. **Cached prices are per currency.** A price cached for one currency must never be served for another.
""")

# order-service: orders, stock, prices, money rules and the nightly settlement job
put("order-service/pom.xml", pom("order-service", [WEB, JDBC, REDIS, FEIGN, BATCH]))
put("order-service/src/main/resources/application.yml", yml("order-service", 8081))
O = "order-service/src/main/java/com/shoplab/order"
C, I, B = f"{O}/rules", f"{O}/stock", f"{O}/billing"
P = "payment-service/src/main/java/com/shoplab/payment"
put(f"{C}/PriceCalculator.java", """package com.shoplab.order.rules;

/** Prices in paise. */
public final class PriceCalculator {
    private PriceCalculator() {
    }

    /** The price after the better of the two discounts; they never stack. Percentages are 0 to 100. */
    public static long discounted(long subtotalPaise, int couponPercent, int loyaltyPercent) {
        int best = Math.max(couponPercent, loyaltyPercent);
        return subtotalPaise - subtotalPaise * best / 100;
    }
}
""")
put(f"{C}/BillSplitter.java", """package com.shoplab.order.rules;

/** Splits a bill between people so the parts add up to the total. */
public final class BillSplitter {
    private BillSplitter() {
    }

    public static long[] split(long totalPaise, int people) {
        if (people <= 0) {
            throw new IllegalArgumentException("people must be positive");
        }
        long[] parts = new long[people];
        long base = totalPaise / people;
        long left = totalPaise % people;
        for (int i = 0; i < people; i++) {
            parts[i] = base + (i < left ? 1 : 0);
        }
        return parts;
    }
}
""")
put(f"{C}/CurrencyConverter.java", """package com.shoplab.order.rules;

/** Converts between rupees and another currency. rate is rupees per one unit of that currency. */
public final class CurrencyConverter {
    private CurrencyConverter() {
    }

    /** Rupee paise to the other currency's cents. */
    public static long fromInr(long paise, double rate) {
        return Math.round(paise / rate);
    }

    /** The other currency's cents to rupee paise. */
    public static long toInr(long cents, double rate) {
        return Math.round(cents * rate);
    }
}
""")
put(f"{C}/Paging.java", """package com.shoplab.order.rules;

/** Pages are numbered from 1. */
public final class Paging {
    private Paging() {
    }

    /** The index of the first row on a page. */
    public static int offset(int page, int size) {
        if (page < 1 || size < 1) {
            throw new IllegalArgumentException("page and size start at 1");
        }
        return (page - 1) * size;
    }
}
""")
put(f"{C}/BusinessDay.java", """package com.shoplab.order.rules;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

/** The business day is the calendar day in India. */
public final class BusinessDay {
    static final ZoneId SHOP_ZONE = ZoneId.of("Asia/Kolkata");

    private BusinessDay() {
    }

    public static LocalDate of(Instant at) {
        return at.atZone(SHOP_ZONE).toLocalDate();
    }
}
""")
put(f"{P}/FraudCheck.java", """package com.shoplab.payment;

/** A payment at the limit is allowed; above it is blocked. */
public final class FraudCheck {
    private FraudCheck() {
    }

    public static boolean allowed(long amountPaise, long limitPaise) {
        return amountPaise <= limitPaise;
    }
}
""")

put(f"{O}/OrderApplication.java", """package com.shoplab.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
""")
put(f"{O}/Order.java", """package com.shoplab.order;

public record Order(long id, long customerId, long productId, String status, long totalPaise, int quantity, int reserved) {
}
""")
put(f"{O}/OrderRepository.java", """package com.shoplab.order;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    private final JdbcClient jdbc;

    public OrderRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Order> findById(long id) {
        return jdbc.sql("SELECT * FROM orders WHERE id = ?").param(id).query(Order.class).optional();
    }

    public List<Order> page(int offset, int size) {
        return jdbc.sql("SELECT * FROM orders ORDER BY id LIMIT ? OFFSET ?").param(size).param(offset).query(Order.class).list();
    }

    public void setStatus(long id, String status) {
        jdbc.sql("UPDATE orders SET status = ? WHERE id = ?").param(status).param(id).update();
    }

    public void setReserved(long id, int reserved) {
        jdbc.sql("UPDATE orders SET reserved = ? WHERE id = ?").param(reserved).param(id).update();
    }
}
""")
put(f"{O}/ProductRepository.java", """package com.shoplab.order;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    private final JdbcClient jdbc;

    public ProductRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Long> priceOf(long productId) {
        return jdbc.sql("SELECT price_paise FROM products WHERE id = ?").param(productId).query(Long.class).optional();
    }

    public List<Long> pricesOf(List<Long> productIds) {
        return jdbc.sql("SELECT price_paise FROM products WHERE id IN (:ids)").param("ids", productIds).query(Long.class).list();
    }
}
""")
put(f"{O}/PaymentClient.java", """package com.shoplab.order;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@FeignClient(name = "payment-service", path = "/payments")
public interface PaymentClient {
    @PostMapping("/charge")
    String charge(@RequestBody ChargeRequest request);

    record ChargeRequest(long orderId, long amountPaise) {
    }
}
""")
put(f"{O}/PriceCache.java", """package com.shoplab.order;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** Prices per product and currency, cached in Redis for ten minutes. */
@Component
public class PriceCache {
    private final StringRedisTemplate redis;

    public PriceCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long get(long productId, String currency) {
        String v = redis.opsForValue().get(key(productId, currency));
        return v == null ? null : Long.valueOf(v);
    }

    public void put(long productId, String currency, long price) {
        redis.opsForValue().set(key(productId, currency), Long.toString(price), Duration.ofMinutes(10));
    }

    static String key(long productId, String currency) {
        return "price:" + currency + ":" + productId;
    }
}
""")
put(f"{O}/OrderService.java", """package com.shoplab.order;

import com.shoplab.order.rules.Paging;
import com.shoplab.order.stock.StockService;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final StockService stock;
    private final PaymentClient payments;

    public OrderService(OrderRepository orders, StockService stock, PaymentClient payments) {
        this.orders = orders;
        this.stock = stock;
        this.payments = payments;
    }

    public List<Order> page(int page, int size) {
        return orders.page(Paging.offset(page, size), size);
    }

    public String pay(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        return payments.charge(new PaymentClient.ChargeRequest(order.id(), order.totalPaise()));
    }

    @Transactional
    public void cancel(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        stock.release(order.productId(), order.reserved());
        orders.setReserved(orderId, 0);
        orders.setStatus(orderId, "CANCELLED");
    }
}
""")
put(f"{O}/OrderController.java", """package com.shoplab.order;

import java.util.List;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping
    public List<Order> list(@RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int size) {
        return service.page(page, size);
    }

    @PostMapping("/{id}/pay")
    public String pay(@PathVariable long id) {
        return service.pay(id);
    }

    @PostMapping("/{id}/cancel")
    public void cancel(@PathVariable long id) {
        service.cancel(id);
    }
}
""")

# payment-service
put("payment-service/pom.xml", pom("payment-service", [WEB, REDIS]))
put("payment-service/src/main/resources/application.yml", yml("payment-service", 8082))
put(f"{P}/PaymentApplication.java", """package com.shoplab.payment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PaymentApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaymentApplication.class, args);
    }
}
""")
put(f"{P}/CardGateway.java", """package com.shoplab.payment;

/** The card processor. Charges with the same idempotency key are only made once. */
public interface CardGateway {
    String charge(String idempotencyKey, long amountPaise) throws GatewayTimeout;

    class GatewayTimeout extends Exception {
    }
}
""")
put(f"{P}/PaymentService.java", """package com.shoplab.payment;

import java.time.Duration;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    static final long LIMIT_PAISE = 5_000_000;
    private final CardGateway gateway;
    private final StringRedisTemplate redis;

    public PaymentService(CardGateway gateway, StringRedisTemplate redis) {
        this.gateway = gateway;
        this.redis = redis;
    }

    /** Charges an order once: the order's key is remembered in Redis for 24 hours. */
    public String charge(long orderId, long amountPaise) throws CardGateway.GatewayTimeout {
        if (!FraudCheck.allowed(amountPaise, LIMIT_PAISE)) {
            throw new IllegalStateException("blocked by the fraud limit");
        }
        String key = keyFor(orderId);
        return gateway.charge(key, amountPaise);
    }

    String keyFor(long orderId) {
        String slot = "idem:" + orderId;
        redis.opsForValue().setIfAbsent(slot, UUID.randomUUID().toString(), Duration.ofHours(24));
        return redis.opsForValue().get(slot);
    }
}
""")
put(f"{P}/PaymentController.java", """package com.shoplab.payment;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/payments")
public class PaymentController {
    private final PaymentService service;

    public PaymentController(PaymentService service) {
        this.service = service;
    }

    @PostMapping("/charge")
    public String charge(@RequestBody ChargeRequest request) throws CardGateway.GatewayTimeout {
        return service.charge(request.orderId(), request.amountPaise());
    }

    public record ChargeRequest(long orderId, long amountPaise) {
    }
}
""")

# stock, inside order-service
put(f"{I}/StockRepository.java", """package com.shoplab.order.stock;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class StockRepository {
    private final JdbcClient jdbc;

    public StockRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public int free(long productId) {
        return jdbc.sql("SELECT free FROM stock WHERE product_id = ?").param(productId).query(Integer.class).optional().orElse(0);
    }

    public void add(long productId, int delta) {
        jdbc.sql("UPDATE stock SET free = free + ? WHERE product_id = ?").param(delta).param(productId).update();
    }
}
""")
put(f"{I}/StockService.java", """package com.shoplab.order.stock;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockService {
    private final StockRepository stock;

    public StockService(StockRepository stock) {
        this.stock = stock;
    }

    /** Reserves up to quantity and returns how many were reserved. */
    @Transactional
    public int reserve(long productId, int quantity) {
        int taken = Math.min(stock.free(productId), quantity);
        stock.add(productId, -taken);
        return taken;
    }

    @Transactional
    public void release(long productId, int quantity) {
        stock.add(productId, quantity);
    }
}
""")
# nightly settlement, inside order-service
put(f"{B}/TaxRates.java", """package com.shoplab.order.billing;

import java.util.Map;

/** GST rate in basis points per state code. */
public final class TaxRates {
    static final Map<String, Integer> RATES = Map.of("KA", 1800, "MH", 1800, "TN", 1200);

    private TaxRates() {
    }

    public static int rateFor(String state) {
        return RATES.getOrDefault(state, 1800);
    }

    /** Tax on an amount, rounded to the nearest paisa. */
    public static long taxOn(long amountPaise, String state) {
        return Math.round(amountPaise * rateFor(state) / 10_000.0);
    }
}
""")
put(f"{B}/Settlement.java", """package com.shoplab.order.billing;

import java.time.LocalDate;

public record Settlement(long orderId, LocalDate businessDay, long amountPaise, long taxPaise) {
}
""")
put(f"{B}/SettlementJobConfig.java", """package com.shoplab.order.billing;

import com.shoplab.order.rules.BusinessDay;
import java.sql.Timestamp;
import javax.sql.DataSource;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.infrastructure.item.ItemProcessor;
import org.springframework.batch.infrastructure.item.database.JdbcBatchItemWriter;
import org.springframework.batch.infrastructure.item.database.JdbcCursorItemReader;
import org.springframework.batch.infrastructure.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.infrastructure.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Nightly settlement: every order of the day gets its business day and tax. All or nothing (rule 9). */
@Configuration
public class SettlementJobConfig {

    record Row(long id, Timestamp placedAt, long totalPaise, String state) {
    }

    @Bean
    JdbcCursorItemReader<Row> orders(DataSource dataSource) {
        return new JdbcCursorItemReaderBuilder<Row>()
            .name("orders")
            .dataSource(dataSource)
            .sql("SELECT id, placed_at, total_paise, state FROM orders WHERE settled = FALSE")
            .rowMapper((rs, n) -> new Row(rs.getLong(1), rs.getTimestamp(2), rs.getLong(3), rs.getString(4)))
            .build();
    }

    @Bean
    ItemProcessor<Row, Settlement> settle() {
        return row -> new Settlement(row.id(), BusinessDay.of(row.placedAt().toInstant()), row.totalPaise(),
            TaxRates.taxOn(row.totalPaise(), row.state()));
    }

    @Bean
    JdbcBatchItemWriter<Settlement> settlements(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<Settlement>()
            .dataSource(dataSource)
            .sql("INSERT INTO settlements (order_id, business_day, amount_paise, tax_paise) VALUES (?, ?, ?, ?)")
            .itemPreparedStatementSetter((s, ps) -> {
                ps.setLong(1, s.orderId());
                ps.setObject(2, s.businessDay());
                ps.setLong(3, s.amountPaise());
                ps.setLong(4, s.taxPaise());
            })
            .build();
    }

    @Bean
    Step settleStep(JobRepository jobs, JdbcCursorItemReader<Row> orders, ItemProcessor<Row, Settlement> settle,
                    JdbcBatchItemWriter<Settlement> settlements) {
        return new StepBuilder("settle", jobs)
            .<Row, Settlement>chunk(100)
            .reader(orders)
            .processor(settle)
            .writer(settlements)
            .build();
    }

    @Bean
    Job settlementJob(JobRepository jobs, Step settleStep) {
        return new JobBuilder("settlement", jobs).start(settleStep).build();
    }
}
""")
commit("Set up the shop: orders, payments, inventory and nightly settlement")

# ---------------------------------------------------------------- seen, found by code checks

put(f"{O}/StatusText.java", """package com.shoplab.order;

public final class StatusText {
    private StatusText() {
    }

    /** What the dashboard shows for an order. */
    public static String label(Order order) {
        if (order.status() == "CANCELLED") {
            return "Cancelled";
        }
        return "Active";
    }
}
""")
commit("Show order status on the dashboard", "seen-rule", "String compared with == (identity, not content)",
       f"{O}/StatusText.java", 'order.status() == "CANCELLED"', "string-identity")

edit(f"{O}/OrderService.java", """    @Transactional
    public void cancel(""", """    public long customerOf(long orderId) {
        return orders.findById(orderId).get().customerId();
    }

    @Transactional
    public void cancel(""")
commit("Look up the customer for an order", "seen-rule", "Optional.get() on findById without a check",
       f"{O}/OrderService.java", "orders.findById(orderId).get()", "optional-get")

put(f"{O}/ShipmentService.java", """package com.shoplab.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ShipmentService {
    private static final Logger log = LoggerFactory.getLogger(ShipmentService.class);
    private final OrderRepository orders;

    public ShipmentService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void markShipped(long orderId, int reserved) {
        try {
            orders.setStatus(orderId, "SHIPPED");
            orders.setReserved(orderId, reserved);
        } catch (RuntimeException e) {
            log.warn("could not mark {} shipped", orderId, e);
        }
    }
}
""")
commit("Mark orders shipped from the warehouse feed", "seen-rule",
       "@Transactional method catches the exception, so a half-done change commits",
       f"{O}/ShipmentService.java", "} catch (RuntimeException e) {", "transaction-swallowed")

put(f"{O}/CartPricer.java", """package com.shoplab.order;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class CartPricer {
    private final ProductRepository products;

    public CartPricer(ProductRepository products) {
        this.products = products;
    }

    /** Total of the products in a cart, in paise. */
    public long total(List<Long> productIds) {
        long sum = 0;
        for (Long id : productIds) {
            sum += products.priceOf(id).orElse(0L);
        }
        return sum;
    }
}
""")
commit("Price carts from the catalog", "seen-rule", "A database query per item in a loop (N+1)",
       f"{O}/CartPricer.java", "products.priceOf(id)", "slow-call-in-loop")

# ---------------------------------------------------------------- seen, logic

edit(f"{C}/Paging.java", "        return (page - 1) * size;", "        return page * size;")
commit("Simplify paging", "seen-logic", "Off by one page: pages start at 1, so page 1 skips the first page of rows",
       f"{C}/Paging.java", "return page * size;", behaviour=True)

edit(f"{B}/TaxRates.java", """        return RATES.getOrDefault(state, 1800);""", """        return RATES.get(state.toUpperCase());""")
commit("Accept state codes in any case", "seen-logic",
       "Map.get returns null for an unknown state; unboxing it to int throws NullPointerException",
       f"{B}/TaxRates.java", "return RATES.get(state.toUpperCase());", behaviour=True)

# ---------------------------------------------------------------- novel: only wrong against this shop's rules

edit(f"{C}/PriceCalculator.java", """        int best = Math.max(couponPercent, loyaltyPercent);
        return subtotalPaise - subtotalPaise * best / 100;""", """        long afterCoupon = subtotalPaise - subtotalPaise * couponPercent / 100;
        return afterCoupon - afterCoupon * loyaltyPercent / 100;""")
commit("Let loyalty members use coupons too", "novel",
       "Coupon and loyalty discounts now stack; rule 1 says only the larger one applies",
       f"{C}/PriceCalculator.java", "return afterCoupon - afterCoupon * loyaltyPercent / 100;", behaviour=True)

edit(f"{C}/BusinessDay.java", "        return at.atZone(SHOP_ZONE).toLocalDate();",
     "        return LocalDate.ofInstant(at, ZoneId.of(\"UTC\"));")
commit("Use one clock for daily reports", "novel",
       "The business day is now the UTC day; rule 2 says India time, so the settlement job files late-evening orders under the wrong day",
       f"{C}/BusinessDay.java", 'LocalDate.ofInstant(at, ZoneId.of("UTC"))', behaviour=True)

edit(f"{C}/BillSplitter.java", """        long base = totalPaise / people;
        long left = totalPaise % people;
        for (int i = 0; i < people; i++) {
            parts[i] = base + (i < left ? 1 : 0);
        }""", """        long each = totalPaise / people;
        for (int i = 0; i < people; i++) {
            parts[i] = each;
        }""")
commit("Make bill splitting simpler", "novel",
       "Leftover paise are dropped, so the parts no longer add up to the total (rule 3)",
       f"{C}/BillSplitter.java", "long each = totalPaise / people;", behaviour=True)

edit(f"{P}/FraudCheck.java", "        return amountPaise <= limitPaise;", "        return amountPaise < limitPaise;")
commit("Tighten the fraud check", "novel",
       "A payment exactly at the limit is now blocked; rule 4 says the limit is inclusive",
       f"{P}/FraudCheck.java", "return amountPaise < limitPaise;", behaviour=True)

edit(f"{O}/OrderService.java", "        stock.release(order.productId(), order.reserved());",
     "        stock.release(order.productId(), order.quantity());")
commit("Return stock to the shelf on cancel", "novel",
       "Cancelling releases the ordered quantity, not what was reserved (rule 5), so back-ordered stock appears from nowhere",
       f"{O}/OrderService.java", "stock.release(order.productId(), order.quantity());")

edit(f"{C}/CurrencyConverter.java", "        return Math.round(paise / rate);", "        return Math.round(paise * rate);")
commit("Show prices in the customer's currency", "novel",
       "Converting from rupees multiplies by the rate instead of dividing (rule 6)",
       f"{C}/CurrencyConverter.java", "return Math.round(paise * rate);", behaviour=True)

edit(f"{P}/PaymentService.java", """        String key = keyFor(orderId);
        return gateway.charge(key, amountPaise);
    }""", """        for (int attempt = 1; ; attempt++) {
            try {
                return gateway.charge(UUID.randomUUID().toString(), amountPaise);
            } catch (CardGateway.GatewayTimeout e) {
                if (attempt == 3) {
                    throw e;
                }
            }
        }
    }""")
commit("Retry payments that time out", "novel",
       "Each retry uses a new idempotency key, so a charge that did go through is made again (rule 7)",
       f"{P}/PaymentService.java", "return gateway.charge(UUID.randomUUID().toString(), amountPaise);")

edit(f"{P}/PaymentService.java", "Duration.ofHours(24));", "Duration.ofMillis(24 * 60 * 60));")
commit("Keep idempotency keys in milliseconds like the rest of the config", "novel",
       "The Redis key now expires after 86.4 seconds instead of 24 hours, so a later retry charges again (rule 7)",
       f"{P}/PaymentService.java", "Duration.ofMillis(24 * 60 * 60)")

edit(f"{O}/PriceCache.java", """        return "price:" + currency + ":" + productId;""", """        return "price:" + productId;""")
commit("Shorten Redis keys for prices", "novel",
       "The cache key drops the currency, so a price cached in one currency is served for another (rule 10)",
       f"{O}/PriceCache.java", 'return "price:" + productId;', behaviour=True)

edit(f"{O}/PaymentClient.java", """    @PostMapping("/charge")""", """    @PostMapping("/charges")""")
commit("Use plural resource names for payments", "novel",
       "The Feign client now calls /payments/charges, which payment-service does not serve: every payment fails with 404 (cross-service)",
       f"{O}/PaymentClient.java", '@PostMapping("/charges")')

edit(f"{B}/SettlementJobConfig.java", """            .writer(settlements)
            .build();
    }

    @Bean
    Job""", """            .writer(settlements)
            .faultTolerant()
            .skip(Exception.class)
            .skipLimit(Integer.MAX_VALUE)
            .build();
    }

    @Bean
    Job""")
commit("Make the settlement run resilient", "novel",
       "The step now skips any failing order and finishes successfully; rule 9 says settlement is all or nothing",
       f"{B}/SettlementJobConfig.java", ".skip(Exception.class)")

# ---------------------------------------------------------------- controls

edit(f"{O}/OrderService.java", """    public String pay(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        return payments.charge(new PaymentClient.ChargeRequest(order.id(), order.totalPaise()));
    }""", """    public String pay(long orderId) {
        Order toPay = orders.findById(orderId).orElseThrow();
        PaymentClient.ChargeRequest request = new PaymentClient.ChargeRequest(toPay.id(), toPay.totalPaise());
        return payments.charge(request);
    }""")
commit("Name the payment request before sending it", "control-refactor", "No behaviour change; anything reported is a false alarm",
       f"{O}/OrderService.java", "PaymentClient.ChargeRequest request = new")

edit(f"{O}/StatusText.java", 'if (order.status() == "CANCELLED") {', 'if ("CANCELLED".equals(order.status())) {')
commit("Compare order status by value", "control-fix", "Fixes the string identity check from the status commit",
       f"{O}/StatusText.java", '"CANCELLED".equals(order.status())', "string-identity")

# ---------------------------------------------------------------- features, clean (anything reported is a false alarm)

put(f"{P}/RefundService.java", """package com.shoplab.payment;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

/** Refunds against a paid order. The total refunded for an order never goes above what was paid. */
@Service
public class RefundService {
    private final StringRedisTemplate redis;

    public RefundService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** Records a refund and returns the total refunded so far. */
    public long refund(long orderId, long amountPaise, long paidPaise) {
        if (amountPaise <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        long already = refunded(orderId);
        if (already + amountPaise > paidPaise) {
            throw new IllegalStateException("refund would exceed the amount paid");
        }
        Long total = redis.opsForValue().increment("refunded:" + orderId, amountPaise);
        return total == null ? already + amountPaise : total;
    }

    public long refunded(long orderId) {
        String v = redis.opsForValue().get("refunded:" + orderId);
        return v == null ? 0 : Long.parseLong(v);
    }
}
""")
commit("Add refunds", "control-feature", "New feature, correct; anything reported is a false alarm",
       f"{P}/RefundService.java", "if (already + amountPaise > paidPaise) {")

put(f"{O}/CouponRepository.java", """package com.shoplab.order;

import java.time.LocalDate;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class CouponRepository {
    private final JdbcClient jdbc;

    public CouponRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    /** The percent off for a coupon that is valid on the given day, if there is one. */
    public Optional<Integer> percentOn(String code, LocalDate day) {
        return jdbc.sql("SELECT percent FROM coupons WHERE code = ? AND valid_from <= ? AND valid_to >= ?")
            .param(code).param(day).param(day).query(Integer.class).optional();
    }

    /** Uses one redemption of a coupon if it has any left; true when one was used. */
    public boolean redeem(String code) {
        return jdbc.sql("UPDATE coupons SET used = used + 1 WHERE code = ? AND used < max_uses")
            .param(code).update() == 1;
    }
}
""")
commit("Add coupons", "control-feature", "New feature, correct; anything reported is a false alarm",
       f"{O}/CouponRepository.java", "valid_from <= ? AND valid_to >= ?")

edit(f"{O}/OrderRepository.java", """    public void setStatus(""", """    /** A customer's most recent orders, newest first. */
    public List<Order> forCustomer(long customerId, long limit) {
        return jdbc.sql("SELECT * FROM orders WHERE customer_id = ? ORDER BY id DESC LIMIT ?")
            .param(customerId).param(limit).query(Order.class).list();
    }

    public void setStatus(""")
put(f"{O}/CustomerOrderController.java", """package com.shoplab.order;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/customers/{customerId}/orders")
public class CustomerOrderController {
    private final OrderRepository orders;

    public CustomerOrderController(OrderRepository orders) {
        this.orders = orders;
    }

    @GetMapping
    public List<Order> recent(@PathVariable long customerId, @RequestParam(defaultValue = "10") long limit) {
        return orders.forCustomer(customerId, limit);
    }

    /** One of the customer's own orders; another customer's order is not found. */
    @GetMapping("/{orderId}")
    public Order one(@PathVariable long customerId, @PathVariable long orderId) {
        return orders.findById(orderId)
            .filter(o -> o.customerId() == customerId)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
""")
commit("Let customers see their orders", "control-feature", "New feature, correct; anything reported is a false alarm",
       f"{O}/CustomerOrderController.java", ".filter(o -> o.customerId() == customerId)")

put(f"{B}/SettlementLock.java", """package com.shoplab.order.billing;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** Only one settlement runs at a time across all instances. A crashed run frees the lock after 30 minutes. */
@Component
public class SettlementLock {
    private static final String KEY = "lock:settlement";
    private final StringRedisTemplate redis;

    public SettlementLock(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean acquire(String owner) {
        return Boolean.TRUE.equals(redis.opsForValue().setIfAbsent(KEY, owner, Duration.ofMinutes(30)));
    }

    /** Frees the lock, but only if this owner still holds it. */
    public void release(String owner) {
        if (owner.equals(redis.opsForValue().get(KEY))) {
            redis.delete(KEY);
        }
    }
}
""")
commit("Stop two settlement runs overlapping", "control-feature", "New feature, correct; anything reported is a false alarm",
       f"{B}/SettlementLock.java", "Duration.ofMinutes(30)")

# ---------------------------------------------------------------- AI only: no check matches, and the code cannot be run alone

edit(f"{P}/RefundService.java", "        if (already + amountPaise > paidPaise) {", "        if (amountPaise > paidPaise) {")
commit("Check each refund against the order total", "ai-only",
       "Only this refund is compared with the amount paid, so several partial refunds can add up to more than was paid (the class comment says the total never goes above it)",
       f"{P}/RefundService.java", "if (amountPaise > paidPaise) {")

edit(f"{O}/CouponRepository.java", "valid_from <= ? AND valid_to >= ?", "valid_from >= ? AND valid_to <= ?")
commit("Tidy the coupon date check", "ai-only",
       "The date comparison is flipped, so only coupons that start on or after the day and end on or before it match: valid coupons are refused",
       f"{O}/CouponRepository.java", "valid_from >= ? AND valid_to <= ?")

edit(f"{O}/CouponRepository.java", "WHERE code = ? AND used < max_uses\")", "WHERE code = ?\")")
commit("Speed up coupon redemption", "ai-only",
       "The update no longer checks uses left, so a coupon can be used past max_uses and redeem() always says one was used",
       f"{O}/CouponRepository.java", 'UPDATE coupons SET used = used + 1 WHERE code = ?")')

edit(f"{O}/CustomerOrderController.java", """        return orders.findById(orderId)
            .filter(o -> o.customerId() == customerId)
            .orElseThrow(""", """        return orders.findById(orderId)
            .orElseThrow(""")
commit("Simplify the order lookup", "ai-only",
       "The ownership filter is gone, so any customer can read any other customer's order by its id (insecure direct object reference)",
       f"{O}/CustomerOrderController.java", "return orders.findById(orderId)")

edit(f"{O}/CustomerOrderController.java", "        return orders.forCustomer(customerId, limit);", "        return orders.forCustomer(limit, customerId);")
commit("Tidy the recent orders endpoint", "ai-only",
       "The arguments are swapped: the limit is used as the customer id and the customer id as the row limit",
       f"{O}/CustomerOrderController.java", "orders.forCustomer(limit, customerId)")

edit(f"{B}/SettlementLock.java", "setIfAbsent(KEY, owner, Duration.ofMinutes(30))", "setIfAbsent(KEY, owner)")
commit("Hold the settlement lock until the run finishes", "ai-only",
       "The lock has no expiry now, so a run that crashes keeps it forever and settlement never runs again (the class comment says 30 minutes)",
       f"{B}/SettlementLock.java", "setIfAbsent(KEY, owner))")

edit(f"{B}/SettlementLock.java", """        if (owner.equals(redis.opsForValue().get(KEY))) {
            redis.delete(KEY);
        }""", """        redis.delete(KEY);""")
commit("Always clear the settlement lock when done", "ai-only",
       "Release deletes the lock without checking the owner, so a slow run can free the lock another run now holds",
       f"{B}/SettlementLock.java", "        redis.delete(KEY);")

out = os.path.join(HERE, "shop-lab-truth.json")
with open(out, "w") as f:
    json.dump(truth, f, indent=1)
print(f"{DEST}: {len(truth) + 1} commits; answer key in {out}")
for t in truth:
    print(f"  {t['sha'][:7]} {t['kind']:16} {t['service']:18} {t['message']}")
