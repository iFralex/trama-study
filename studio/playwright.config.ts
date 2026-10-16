import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests/e2e',workers:1,use:{baseURL:process.env.STUDIO_TEST_URL??'http://127.0.0.1:4327',launchOptions:{executablePath:process.env.STUDIO_CHROME},headless:true},reporter:'list'});
