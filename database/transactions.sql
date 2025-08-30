CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(255) NOT NULL,
    entity_id VARCHAR(255),
    amount DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(50),
    notes TEXT,
    details_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL
);