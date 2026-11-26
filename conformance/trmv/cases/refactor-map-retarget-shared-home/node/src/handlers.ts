import {
  FlightCatalog, // the catalog
  FlightSchema,
  FlightTable,
} from './flight';

export const all = [new FlightCatalog(), new FlightSchema(), new FlightTable()];
